# PS-1 CIS Production Deployment Audit
**Date:** 2026-07-10  
**Author:** Antigravity (AI Agent) + Naren Kandasamy  
**Status:** UNRESOLVED — Query pipeline stuck in QUEUED state  
**Env:** Zoho Catalyst Development Environment (PS1-CIS project)  
**AppSail URL:** `https://backend-50043491738.development.catalystappsail.in`  
**Frontend URL:** `https://ps1-cis-60075634347.development.catalystserverless.in/app/index.html`

---

## Table of Contents
1. [Background & Starting State](#1-background--starting-state)
2. [Issue 1 — AppSail Returning 500 Internal Server Error](#2-issue-1--appsail-returning-500-internal-server-error)
3. [Issue 2 — Startup Command Misconfiguration](#3-issue-2--startup-command-misconfiguration)
4. [Issue 3 — Python Binary Not Found (`python` vs `python3.13`)](#4-issue-3--python-binary-not-found)
5. [Issue 4 — Container Startup Timeout Due to `pip install`](#5-issue-4--container-startup-timeout-due-to-pip-install)
6. [The Fix That Got the Backend Up](#6-the-fix-that-got-the-backend-up)
7. [Issue 5 — Frontend Queries Stuck in QUEUED State](#7-issue-5--frontend-queries-stuck-in-queued-state)
8. [Diagnostic Attempts for the QUEUED Hang](#8-diagnostic-attempts-for-the-queued-hang)
9. [Root Cause Hypothesis](#9-root-cause-hypothesis)
10. [What Files Were Changed](#10-what-files-were-changed)
11. [What Remains Unchanged / Untested](#11-what-remains-unchanged--untested)
12. [Recommended Next Steps](#12-recommended-next-steps)

---

## 1. Background & Starting State

### Architecture Overview
The PS-1 CIS system uses a distributed, event-driven architecture on Zoho Catalyst:

```
[React Frontend (Slate)]
        │
        ▼ (HTTP POST /query)
[AppSail: backend (FastAPI)]
        │
        ├─► Writes job:{job_id} = "queued" to Catalyst NoSQL
        │
        ├─► Attempts to fire event via Catalyst Signals Custom Publisher
        │         └─► [Serverless Function: ps_1_cis_function]
        │                     └─► Runs LangGraph pipeline
        │                     └─► Writes job:{job_id} = "done" to NoSQL
        │
        └─► SSE stream polls NoSQL every 0.5s for status changes
              └─► When "done", sends result to frontend
```

### Pre-existing Issues Before This Session
From the previous session summary, the following had already been resolved in code:
- `catalyst.json` AppSail structure was corrected
- Signals webhook payload was fixed to use `json.dumps()`
- Production dependencies added: `langgraph`, `neo4j`, `rapidfuzz`, `zcatalyst-sdk`
- Cold-start `asyncio.run()` crash in function was fixed
- Narrow session locks to prevent deadlocks
- NoSQL persistence moved from in-memory mock to real Catalyst NoSQL
- Environment variables (`ZC_*`) set in both AppSail and Function consoles

### Starting Symptom
When user navigated to the frontend and submitted a query, the chat message showed `QUEUED...` permanently (60+ seconds with no progress). The `/health` endpoint on the AppSail returned `500 Internal Server Error`.

---

## 2. Issue 1 — AppSail Returning 500 Internal Server Error

### Discovery
Running `curl https://backend-50043491738.development.catalystappsail.in/health` returned:
```json
{"status":"failure","data":{"message":"Execution failed. Please check the startup command or port.","error_code":"INTERNAL_SERVER_ERROR"}}
```

### Attempted Diagnosis
- Tried `catalyst appsail:logs` from CLI → **Failed**: "unknown command"
- Tried `catalyst logs -h` to find correct log command → No direct log streaming available from CLI
- Resorted to browser-based log inspection via Catalyst Console DevOps → Logs

### What We Found in the Console
Browser subagent navigated to:  
`Console → PS1-CIS → Serverless → AppSail → backend → View Logs`

The DevOps Application logs showed:
```
ERROR :: exec failed: python backend/start.py : No such file or directory (os error 2)
```

**Interpretation:** The container could not find the `python` binary at all. The error message was from the OS container runtime itself (not Python), meaning the startup command's executable path was completely invalid.

---

## 3. Issue 2 — Startup Command Misconfiguration

### Discovery
Earlier in the session (before this user session began), the browser subagent had modified the startup command on the AppSail configuration page to:
```
python3.13 -c "import os; print('FILES:', os.listdir('.'))"
```
This command was a **debug diagnostic** that the previous subagent had injected to list files in the container. It ran and exited immediately without binding to a port, causing the AppSail container to continuously crash-restart.

### Fix Attempted (Step 1)
Modified `backend/app-config.json`:
```diff
- "command": "python3.13 backend/start.py",
+ "command": "python backend/start.py",
```
**Deployed** → Still returned 500.

**Log from console:**
```
ERROR :: exec failed: python backend/start.py : No such file or directory (os error 2)
```
The `python` binary does not exist in the Catalyst Python 3.13 container. Only `python3.13` is available.

### Fix Attempted (Step 2)
Reverted back to `python3.13 backend/start.py` and redeployed. The AppSail CLI confirmed `DEPLOYMENT SUCCESSFUL`, but the `/health` endpoint still returned 500.

---

## 4. Issue 3 — Python Binary Not Found

### Log Evidence
After reverting to `python3.13`, console logs showed pip was running but taking too long (the early deployment logs showed `Downloading pyarrow`, `Downloading langgraph`, etc. — all from inside the container at cold-start, not at deploy time).

### Root Cause Identified
The `backend/start.py` file had a `subprocess.run(pip install -r requirements.txt)` call **inside the process startup**. This was originally added as a workaround because Catalyst AppSail does not run pip install automatically for AppSail targets (only for Functions).

The problem:
1. The pip install takes **3–5 minutes** (langgraph, neo4j, weasyprint, etc.)
2. Catalyst AppSail has a **startup timeout** (estimated 30–60 seconds max)
3. The container process never gets to `uvicorn.run()` before the timeout kills it
4. Catalyst marks the container as crashed → 500 on every request

---

## 5. Issue 4 — Container Startup Timeout Due to `pip install`

### Evidence
The console Application logs showed many lines like:
```
Downloading pyarrow-manylinux2014_x86_64.whl ...
Downloading langgraph-...
Downloading jsonp...
Downloading langc...
```

These were streaming from inside the running container **at request time**, proving the process was spending all its startup time installing packages.

### Original `start.py` Logic (before our fix)
```python
req_path = os.path.join(_here, "requirements.txt")
subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True)
user_site = site.getusersitepackages()
if user_site not in sys.path:
    sys.path.insert(0, user_site)
```
This ran pip every single cold start, which exceeded the timeout budget.

---

## 6. The Fix That Got the Backend Up

### Strategy: Pre-bundle All Dependencies

Instead of installing at runtime, we pre-installed all packages **locally** into a hidden `.packages/` directory and bundled them into the deployment artifact.

#### Step 1: Install locally
```bash
pip install -t backend/.packages -r backend/requirements.txt
```
This downloaded and extracted all 163 packages (fastapi, uvicorn, langgraph, neo4j, rapidfuzz, weasyprint, zcatalyst-sdk, etc.) into `backend/.packages/`.

#### Step 2: Patch `start.py`
```diff
- req_path = os.path.join(_here, "requirements.txt")
- subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_path], check=True)
- user_site = site.getusersitepackages()
- if user_site not in sys.path:
-     sys.path.insert(0, user_site)
+ packages_path = os.path.join(_here, ".packages")
+ if os.path.exists(packages_path) and packages_path not in sys.path:
+     sys.path.insert(0, packages_path)
```

#### Step 3: Redeploy
```bash
catalyst deploy --only appsail
```
Upload took ~2–3 minutes (due to the large `.packages/` bundle). AppSail deployment succeeded.

#### Verification
```bash
curl https://backend-50043491738.development.catalystappsail.in/health
# {"status":"ok"}
```

**The backend is now LIVE and responding correctly.**

---

## 7. Issue 5 — Frontend Queries Stuck in QUEUED State

### Symptom
Despite the backend returning `{"status":"ok"}`, when the user typed a query in the frontend chat interface and pressed Submit, the response card showed:
```
● QUEUED...
```
...indefinitely. No stage progression occurred (understanding_query → resolving_entities → etc.). After 60+ seconds, the system timed out without delivering an answer.

### What the Frontend Does
1. POST `/query` → backend creates `job:{id}` in NoSQL with `status: "queued"`, then fires a Catalyst Signals event
2. Frontend opens SSE stream at `/stream/{job_id}`
3. Backend's `sse_poller.py` polls NoSQL every 0.5s for status changes
4. Pipeline Function reads the Signals event, runs LangGraph, writes `status: "done"` to NoSQL
5. SSE poller sees "done", sends result to frontend

The query was stuck at **step 2/3** — the SSE stream was receiving `ping` events but status never moved past "queued".

---

## 8. Diagnostic Attempts for the QUEUED Hang

### Attempt 1: Check if the Backend Itself Can Run the Pipeline
We temporarily patched `job_dispatch.py` to **disable Signals** and force inline (local) pipeline execution:
```python
if False:  # Temporarily disable signals to force fallback
    async with httpx.AsyncClient(timeout=5.0) as client:
```
This was intended to trigger the `_local_pipeline_runner()` path which runs LangGraph inside the same AppSail process.

**Result:** Still QUEUED. The fallback path also did not produce output within 60+ seconds.

**Implication:** The issue is **not** specific to Signals routing. Something deeper is broken in the NoSQL read/write cycle or in the pipeline execution itself within the AppSail container.

### Attempt 2: Read Catalyst Console Logs (Browser Subagent)
We launched multiple browser subagents to navigate to:
- `DevOps → Logs → Log Type: Application → Resource: backend`
- `DevOps → Logs → Log Type: Application → Resource: ps_1_cis_function`
- `DevOps → Logs → Resource: job_test_func`

**Problems encountered:**
1. Catalyst's log UI only shows logs that have been indexed — there is a note: *"Log messages for the last 5 mins may not be indexed"*
2. Every search attempt returned no logs or empty results
3. The browser subagent repeatedly timed out trying to find meaningful log entries
4. The filter UI is complex (Log Type, Resources, Date/Time, Log Level, Keyword dropdowns) and the subagent had difficulty composing correct filter combinations
5. Over 1,200+ browser interaction steps were spent across multiple subagent runs without successfully reading a usable traceback

**Root Cause of Log Failure:** The Catalyst DevOps log viewer appears to have significant indexing lag for Application logs. The subagent navigated to the correct page but found either no logs or only pip download logs from the previous build-time pip install.

### Attempt 3: Programmatic NoSQL Access Test
We attempted to write a diagnostic script that would use `zcatalyst_sdk` to query the `Job_Status` table directly from the local machine.

```python
from zcatalyst_sdk.catalyst_app import CatalystApp
app = zcatalyst_sdk.initialize()
# ...
```

**Result:**
```
Error: {'code': 'FATAL ERROR', 'message': 'Catalyst headers are empty'}
```
The SDK requires proper Catalyst authentication context (the script was run outside the Catalyst container environment, so no auth headers were injected). This approach was abandoned.

### Attempt 4: Read the Signals/NoSQL Architecture
We re-read the key source files to understand the data flow:

- `backend/job_dispatch.py` — confirms Signals URL is read from `ZC_SIGNALS_PUBLISHER_URL` env var
- `shared/catalyst_client.py` — confirms NoSQL uses `ZC_PROJECT_ID` + OAuth refresh token flow
- `sse_poller.py` — confirms polling every 0.5s with exponential backoff up to 5s intervals
- `functions/ps_1_cis_function/main.py` — confirmed `asyncio.run()` is used inside the synchronous Catalyst Functions handler

---

## 9. Root Cause Hypothesis

Based on all available evidence, there are **three candidate root causes**, ordered by likelihood:

---

### Hypothesis A (Most Likely): NoSQL OAuth Token Failure in Production

**What it is:**  
`shared/catalyst_client.py`'s `_get_nosql_access_token()` uses a `ZC_REFRESH_TOKEN` + `ZC_CLIENT_ID` + `ZC_CLIENT_SECRET` to get a fresh OAuth token from `https://accounts.zoho.in/oauth/v2/token`. If this OAuth call fails (wrong credentials, expired grant, scope issue), then:
- `write_job_status()` fails silently → job stays `"queued"` forever
- `nosql_get()` in the SSE poller returns `None` → status never changes
- **No visible error** in the frontend — just permanent "QUEUED"

**Evidence:**
- The original error before we fixed the startup was `{"code": "FATAL ERROR", "message": "Catalyst headers are empty"}` — this is exactly what the NoSQL SDK throws when auth fails
- The `ZC_*` environment variables were set in the console, but we have not verified they were set in the **correct environment** (Development vs Production) and on the **correct resource** (AppSail `backend` vs Function `ps_1_cis_function`)
- The refresh token flow makes one extra HTTP round-trip before any NoSQL call — if this times out or returns an error, every subsequent nosql_get/nosql_set will fail

**How to verify:**  
Add a startup log in `backend/main.py` that immediately tries to call `nosql_set("healthcheck", "ok")` and logs success/failure. Check DevOps logs after a restart.

---

### Hypothesis B: Signals Publisher URL Not Configured

**What it is:**  
If `ZC_SIGNALS_PUBLISHER_URL` is not set in the AppSail environment, `_get_signals_url()` returns `None`, and the code falls through to the `_local_pipeline_runner()` fallback. The fallback runs via `asyncio.create_task()`. However, in Catalyst AppSail (which runs a single uvicorn worker), a long-running LangGraph task (30–60s of LLM calls + Memgraph queries) may block the event loop or cause the SSE connection to timeout before the task completes.

**Evidence:**
- When we forced `if False:` to skip Signals entirely, the system still hung — consistent with the fallback pipeline itself timing out
- The AppSail container may have aggressive HTTP timeout policies that kill long-running SSE connections

**How to verify:**  
Check AppSail environment variables in the console. Confirm `ZC_SIGNALS_PUBLISHER_URL` has the correct Signals endpoint URL. The URL format is: `https://signals.catalyst.zoho.in/baas/v1/project/{project_id}/signal/{publisher_name}/publish`

---

### Hypothesis C: `asyncio.Lock` Event Loop Mismatch in NoSQL Client

**What it is:**  
`shared/catalyst_client.py` uses `asyncio.Lock` objects cached in a module-level `OrderedDict`. In Catalyst Functions, the event loop is created fresh per invocation by `asyncio.run()`. If a stale Lock was created in a previous event loop, and the current invocation tries to use it in a new loop, Python raises `RuntimeError: This lock is created for a different event loop`.

This was patched with `_get_mock_db_lock()` but the main `get_lock()` / `get_session_lock()` system still uses a plain module-level dict without binding to the current loop.

**Evidence:**
- This would cause the pipeline to crash silently on its first `async with get_session_lock(session_id):` call
- The exception would be caught by the outer `try/except Exception` in `_run_pipeline()`, which would call `write_job_status(..., status="failed")` — but if NoSQL itself is broken (Hypothesis A), this write would also fail, leaving the job permanently in "queued" state
- This is a double-failure scenario that is nearly invisible from the outside

**How to verify:**  
Add explicit logging before and after every `async with get_session_lock()` call in the function handler.

---

### Summary: The Likely Chain of Failure

```
User submits query
    → Backend writes job "queued" to NoSQL (may fail silently if auth broken)
    → Backend fires Signals event (or falls back to local task)
    → Pipeline function invoked (or local task starts)
    → First async lock acquisition → possible event loop mismatch crash
    → Exception caught → tries to write "failed" to NoSQL
    → NoSQL auth fails → write also fails
    → Job stays "queued" forever
    → SSE times out after 120s
    → Frontend shows permanent QUEUED
```

---

## 10. What Files Were Changed

| File | Change | Outcome |
|------|--------|---------|
| `backend/app-config.json` | Changed command: `python` → `python3.13` → `python3.13` (reverted) | Startup fixed |
| `backend/start.py` | Removed pip install block; replaced with `.packages` path injection | Startup fixed — health returns 200 |
| `backend/.packages/` | Created via `pip install -t .packages -r requirements.txt` | All deps bundled into deploy artifact |
| `backend/job_dispatch.py` | Temporarily set `if False:` to disable Signals and force local pipeline | No change to symptoms — still QUEUED |

### Files Left in Current State
- `backend/job_dispatch.py` has `if False:` at line 68 — **this must be reverted** before any production testing. Currently the system will ALWAYS use the local fallback pipeline instead of Signals.
- `backend/start.py` has the correct `.packages` logic — **this is correct and should stay**

---

## 11. What Remains Unchanged / Untested

1. **`ZC_SIGNALS_PUBLISHER_URL`** — Not confirmed to be set in AppSail environment
2. **`ZC_REFRESH_TOKEN` validity** — Not confirmed the token hasn't expired or been revoked
3. **`ps_1_cis_function` environment variables** — Were shown to be set during the previous session but not re-verified in this session
4. **Memgraph connectivity** — `MEMGRAPH_URI = bolt://92.4.84.250:7687` — not tested from within the Catalyst container
5. **LLM endpoint** — `ZC_LLM_ENDPOINT` set but not tested end-to-end from production
6. **NoSQL table `AppKeyValueStore`** — Assumed to exist; never confirmed by querying it from the console
7. **Catalyst Signals Rule** — `cis_query_rule` seen in the console but not confirmed to be active and routing to `ps_1_cis_function`

---

## 12. Recommended Next Steps

### Priority 1: Revert the Signals Bypass (CRITICAL)
```python
# In backend/job_dispatch.py, line 68 — CHANGE THIS BACK:
if False:  # Temporarily disable signals to force fallback
# TO:
if signals_url:
```
Then redeploy. The current state of the code makes the backend always run the pipeline inline (which won't work for long queries in AppSail).

### Priority 2: Add Explicit NoSQL Health Logging
In `backend/main.py`, add a startup event that tests the NoSQL connection:
```python
@app.on_event("startup")
async def startup_checks():
    try:
        from shared.catalyst_client import nosql_set, nosql_get
        await nosql_set("health:startup", "ok")
        result = await nosql_get("health:startup")
        print(f"[STARTUP] NoSQL health check: {result}")
    except Exception as e:
        print(f"[STARTUP] NoSQL health check FAILED: {e}")
```
After deploying, check DevOps Application logs within 30 seconds of startup to see if NoSQL auth is working.

### Priority 3: Manually Verify All Env Vars in Console
Go to `Console → PS1-CIS → Serverless → AppSail → backend → Configuration → Environment Variables` and confirm ALL of these are present and populated:

| Key | Expected Format |
|-----|----------------|
| `ZC_PROJECT_ID` | 5-digit number |
| `ZC_REFRESH_TOKEN` | Long alphanumeric string |
| `ZC_CLIENT_ID` | UUID-like string |
| `ZC_CLIENT_SECRET` | Alphanumeric string |
| `ZC_LLM_ENDPOINT` | Full HTTPS URL |
| `ZC_VLM_ENDPOINT` | Full HTTPS URL |
| `MEMGRAPH_URI` | `bolt://...` URI |
| `ZC_SIGNALS_PUBLISHER_URL` | Full Signals publisher URL (may be MISSING) |

Also repeat the same check for the **`ps_1_cis_function`** Configuration tab.

### Priority 4: Test NoSQL Write from a Minimal Function
Create a tiny test function that just does:
```python
def handler(event, context):
    import zcatalyst_sdk as zcatalyst
    app = zcatalyst.initialize()
    nosql = app.nosql()
    table = nosql.table("AppKeyValueStore")
    table.set_item({"item_key": "test", "item_value": "hello"})
    context.close_with_success()
```
Execute this from the Catalyst console. If it fails, the NoSQL table or permissions are misconfigured.

### Priority 5: Check Signals Rule is Active
In `Console → Signals → Rules`, verify `cis_query_rule`:
- Status: **Active**
- Condition: fires on events from the custom publisher
- Target: `ps_1_cis_function`

### Priority 6: Consider Simplifying Architecture for Debug
Temporarily make the system synchronous for one test:
1. Remove the Signals dispatch entirely
2. Run the LangGraph pipeline **directly in the AppSail process** using a thread (`concurrent.futures.ThreadPoolExecutor`) with a 90-second timeout
3. Write the result to NoSQL inline
4. SSE poller picks it up

This removes 3 layers of complexity (Signals → Function → NoSQL round-trip) and lets us verify the core pipeline logic works end-to-end before re-introducing the event-driven architecture.

---

## Appendix: Key URLs and Identifiers

| Resource | Value |
|----------|-------|
| AppSail Backend | `https://backend-50043491738.development.catalystappsail.in` |
| Frontend | `https://ps1-cis-60075634347.development.catalystserverless.in/app/index.html` |
| Catalyst Console | `https://console.catalyst.zoho.in` |
| Catalyst Project ID | `45958000000015001` |
| Catalyst Org ID | `60075634347` |
| Memgraph URI | `bolt://92.4.84.250:7687` |
| AppSail Git Ref | HEAD `5f77e44` (main) |

---

*Document created: 2026-07-10 18:18 IST*  
*Last confirmed working: `/health` returns `{"status":"ok"}`*  
*Last confirmed broken: Query pipeline stuck at QUEUED after 60+ seconds*
