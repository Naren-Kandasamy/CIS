# PS-1 CIS — Full Codebase Audit Report

**Date:** 2026-07-04
**Auditor:** Claude (Sonnet 5), audit-only pass — no code modified
**Scope:** Every tracked source file in the repository, read and analyzed individually (121 files: `backend/`, `pipeline_function/`, `shared/`, `ingestion/`, `functions/`, `data/scripts/`, `client/`, all root-level scripts, and config files). Binary assets, lockfiles, and font files were excluded from line-by-line review.
**Method:** Every finding below was verified by reading the actual current file content directly — not by trusting the "fixed" claims in the three prior audit reports (`Docs/CIS_audit_report.md`, `Docs/Phase3_Audit_Report.md`, `Docs/Codebase_Audit_v2.md`). Several findings below exist specifically *because* a prior doc's "fixed" claim turned out to be true for one copy of a duplicated file but not another, or because a "working correctly" claim didn't hold up once the exact route/path string was checked. Those are called out explicitly.

---

## How to read this report

- **Verified-fixed**: I independently re-read the current file and confirmed the fix described in a prior audit is actually present in the code today.
- **Verified-still-broken**: I independently re-read the current file and confirmed a previously-reported bug is still present, despite being claimed fixed (or never having a fix applied).
- **New finding**: Not previously reported by any prior audit doc.

---

## 🔴 CRITICAL

### C1. Hardcoded live-looking Zoho Catalyst API token committed to git, in 4 files
**Files:** `test_catalyst.py:5`, `test_llm.py:5`, `test_llm_json.py:5`, `test_sdk.py:4` (also `.catalystrc`, tracked despite listing itself in `.gitignore`)
**Category:** Other (security / secret leak)
**New finding.**

All four files hardcode the identical literal string:
```python
token = "<REDACTED — real token value present in the source files>"
```
This is committed to git (confirmed via `git log --oneline -- test_catalyst.py test_sdk.py test_llm.py test_llm_json.py .catalystrc`, present since the "Initial Commit" and touched again in a later commit) and is currently tracked in the working tree (`git ls-files` lists all of these). `.gitignore` explicitly lists `test_sdk.py`, `test_catalyst.py`, `test_llm*.py`, and `.catalystrc` as patterns to ignore — meaning the team recognized these as sensitive/scratch and tried to exclude them, but never ran `git rm --cached`, so they remain committed and (per `git status`, branch tracks `origin/main`) pushed to the remote. This directly violates `Agents.md`'s explicit rule: "never hardcode credentials, and never echo `.env` contents into a response or commit."
**Severity: Critical** — a real (or real-looking) production credential is permanently in git history, retrievable by anyone with repo access regardless of any future rotation of the working tree files. Recommend rotating this token immediately regardless of the audit-only scope of this pass.

### C2. The actually-deployed Catalyst Function skips the Confidence Engine entirely
**Files:** `functions/ps_1_cis_function/main.py` (deployed entrypoint, confirmed via `catalyst.json`'s `functions.targets` and its own `catalyst-config.json`) → imports and runs `pipeline_function/pipeline/template_router.py::run_template_router`
**Category:** Mock-stub / architectural drift
**New finding — and it invalidates the "launch blocker cleared" result in `data/scripts/verify_trap_scenario.py`.**

`catalyst.json` registers `ps_1_cis_function` as a real deployment target, and `functions/ps_1_cis_function/main.py`'s `_run_pipeline()` calls `run_template_router()`, not `run_langgraph_pipeline()`. I read `template_router.py` in full: it builds `evidence` dicts with only `source`, `fir_id`, `data` fields — it never imports or calls `run_confidence_engine` anywhere, and never attaches a `confidence` field to any evidence item.

Meanwhile, `data/scripts/verify_trap_scenario.py` — described in `Final_Checklist_Review.md`'s language as clearing a "launch blocker" — imports `run_langgraph_pipeline` from `langgraph_router.py`, **not** `run_template_router`. That test asserts trap FIRs (two unrelated burglaries with an identical MO) must NOT be scored "high"/"medium" confidence, specifically to guard against the system confidently linking unrelated crimes. Since the actually-deployed function never runs the confidence engine at all, that safety check has never been exercised against the code path that is actually deployed to Zoho Catalyst. If the trap query hit the real deployed function, there would be no `confidence` key present on the evidence items to even check.
**Severity: Critical** — the system's core safety mechanism against false-positive criminal linkage (the entire point of the Confidence Engine per Architecture §10/11) is absent from the code path that ships.

### C3. Job-status persistence ("NoSQL") is two disconnected in-memory dicts — the primary query flow cannot work across a real Catalyst deployment
**Files:** `backend/job_dispatch.py:13` (`_nosql_mock_db = {}`), `shared/catalyst_client.py:228` (`_mock_nosql_cache = {}`)
**Category:** Mock-stub
**New finding**, though it explains and is corroborated by the still-unchecked item in `Docs/Final_Checklist_Review.md`: *"[ ] Full Catalyst Deployment Verified: Run a full compound query end-to-end in the cloud to confirm the AppSail SSE poll successfully picks up the 'done' status from the Event Function."*

`backend/job_dispatch.py` literally comments `# Mocking NoSQL logic for week 1 skeleton` above a plain in-process Python dict used for job status. `pipeline_function/main.py` and `functions/ps_1_cis_function/main.py` (the pipeline entrypoints, run as a **separate** Zoho Catalyst Function per `Agents.md`'s architecture) both `import write_job_status`/`nosql_get`/`nosql_set` **from `backend.job_dispatch`** — i.e., the pipeline Function's status writes depend on cross-process access to the AppSail backend's private in-memory dict. In local dev this "works" only because `_local_pipeline_runner` in `job_dispatch.py` runs the pipeline inline via `asyncio.create_task` in the **same** Python process as the backend, so it's the same dict in memory. In a real Catalyst deployment, AppSail and the Function are separate containers/processes with no shared memory — the Function's writes would go to an empty dict in its own process, and the AppSail SSE poller (which reads from its own separate dict) would never see them. Every query would time out after 120s in production. A second, entirely separate in-memory mock (`shared/catalyst_client.py::_mock_nosql_cache`) exists for cache/LLM-cache purposes — two independent fake "NoSQL" layers, neither backed by a real Catalyst Data Store table.
**Severity: Critical** — this is the persistence layer the entire query/response flow depends on; it has apparently never been wired to a real backing store.

### C4. `vlm_extract` silently returns a fabricated, realistic FIR record on any failure
**File:** `shared/catalyst_client.py:93-118`
**Category:** Mock-stub
**New finding** (this function did not exist at the time of the prior three audits — it's part of the "add multimodal endpoints" work in the latest commit).

```python
async def vlm_extract(image_bytes, prompt, system) -> str:
    url = CATALYST_VLM_URL()
    if not url:
        return '{"FIR_Number": "124/2023", ... "Accused": "Suresh (Suri)", ...}'
    ...
    except Exception as e:
        print(f"[Mock VLM] Catalyst VLM failed ({e}), returning mock FIR data.")
        return '{"FIR_Number": "124/2023", ... "Accused": "Suresh (Suri)", ...}'
```
Whether the VLM endpoint is unconfigured OR the real call throws for any reason (timeout, auth failure, malformed response), this function returns the exact same specific, plausible-looking fabricated police record. `backend/api/routes/ocr.py` passes this straight back as `{"extracted": result}` with no "mock"/"degraded" flag anywhere in the response. An officer uploading a real FIR photo during a demo or real use, if the VLM call fails for any transient reason, would receive a fabricated case record with no indication it isn't real.
**Severity: Critical** — silently fabricated police-record data indistinguishable from genuine OCR output, in a system whose stated design principle (Agents.md §6) is "never invent connections not in evidence."

### C5. All LLM traffic can be silently rerouted to a third-party provider (Groq) or a local Ollama instance
**File:** `shared/catalyst_client.py:38-72`, wraps into `pipeline_function/pipeline/catalyst_resilient_client.py::llm_complete_resilient` which every pipeline stage uses (NER, DAG planning, synthesis)
**Category:** Other (architecture/data-handling violation)
**New finding.**

```python
if os.getenv("LOCAL_MOCK_MODE") == "true":
    # routes to http://localhost:11434 (Ollama) ...
groq_key = os.getenv("GROQ_API_KEY")
if groq_key:
    # routes to https://api.groq.com/openai/v1/chat/completions with llama-3.3-70b-versatile ...
```
Both diversions sit underneath `llm_complete_resilient`, so if `GROQ_API_KEY` happens to be set in the environment (plausible leftover from local development against a rate-limited Catalyst endpoint), **every** LLM call in the entire pipeline — NER/intent extraction, DAG planning, and final synthesis of case data — is silently sent to Groq's third-party US-hosted API instead of the documented Zoho Catalyst Qwen model, with no log line, response marker, or architecture-doc mention of Groq anywhere. For a law-enforcement intelligence system, sending query content (which can include names, locations, case details) to an undocumented third-party AI provider based on an ambient environment variable is a meaningful, silent data-handling risk.
**Severity: Critical** — silent provider substitution for every LLM call in the system, with no observability, for a system handling police case data.

### C6. Structured/SQL (ZTSQL) retrieval is disconnected end-to-end — three mutually-inconsistent schemas across write and read paths
**Files:** `ingestion/pipeline.py:39-56` (writes to table `Firs`, flat `district_name`), `pipeline_function/pipeline/retrieval/executor.py:106-126` (`run_sql_step`, queries table `cases`, assumes flat `district_name`), `pipeline_function/pipeline/retrieval/sql_client.py` (queries `cases` JOIN `units` via `district_id` — no flat column at all), `data/scripts/ingest_all.py:13-30` and `data/scripts/plant_trap_scenario.py:39-44` (write to `cases`, no `district_name` column)
**Category:** Mock-stub / other (broken feature)
**Builds on and supersedes CIS_audit_report.md's BUG-05** ("SQL Schema Mismatch," previously rated High) — independently re-verified against current code and found to be worse and in a different location than the original report identified.

The original BUG-05 fix (a JOIN through `units`) was applied only to `sql_client.py` — but I confirmed via `grep` that `sql_client.py`'s functions (`get_accused_stats`, `search_cases_by_district`) have **no callers anywhere in the codebase** except a stale comment in `executor.py` ("Since `search_cases_by_district` doesn't exist yet, we mock..." — it does exist, the comment is just outdated). The code that's actually invoked live, `executor.py::run_sql_step`, has its own independent, never-fixed inline query: `SELECT * FROM cases WHERE district_name LIKE ?` — the exact same flat-column assumption the original bug described. Separately, `ingestion/pipeline.py` — the script wired as the official ingestion entrypoint via `catalyst.json`'s `"scripts": {"ingest": "python ingestion/pipeline.py"}` — inserts into a table literally named `Firs` (capitalized, different name entirely) with columns `(fir_internal_id, crime_no, district_name, incident_date, crime_sub_head_name)`. The dataset-seeding scripts that are actually used per `Final_Checklist_Review.md`'s "[x] Full KB & ZTSQL Hydration" (`data/scripts/ingest_all.py`, `plant_trap_scenario.py`) write into `cases` instead, without a `district_name` column. No two of these four pieces of code agree on table name or schema shape. Every failure mode in this chain (`ztsql_query`'s `if not url: return []`, its 404-to-`[]` fallback, and its broad `except Exception: return []`) degrades silently to an empty list, which is why this has evidently gone unnoticed through three rounds of prior audits.
**Severity: Critical** — the entire structured-retrieval feature is non-functional end-to-end, and its failure is invisible by design (empty list, not an error).

---

## 🟠 HIGH

### H1. The deployed Catalyst Function still has the "sys.path in hot loop" and "warm_connections never called" bugs — fixed only in the sibling file
**File:** `functions/ps_1_cis_function/main.py:25-30, 39-47`
**Category:** Other / performance
**Verified-still-broken** — Phase3_Audit_Report.md's Bug #2 and Bug #3 were fixed in `pipeline_function/main.py` (confirmed: `sys.path.insert` moved to module level, `asyncio.run(warm_connections())` called at import time) but `functions/ps_1_cis_function/main.py` — the file Catalyst actually deploys — still has `sys.path.insert(...)` inside `_run_pipeline()` (called on every invocation) and defines `warm_connections()` at the bottom of the file without ever calling it.
**Severity: High** — this is the file that actually ships; every warm-container invocation re-inserts into `sys.path` and never gets Memgraph connection warm-up, contradicting Implementation §12's explicit requirement.

### H2. Entity resolution in the deployed pipeline is still sequential, not parallelized
**File:** `pipeline_function/pipeline/template_router.py:20-31`
**Category:** Race condition / performance
**Verified-still-broken.** Phase3_Audit_Report.md's Bug #8 (sequential `for` loops instead of `asyncio.gather`) was fixed in `langgraph_router.py` and (later) in `graph_definition.py` — both independently re-confirmed by reading the current files. But `template_router.py`, which is what the deployed function (`functions/ps_1_cis_function/main.py`) actually runs, still has plain sequential loops:
```python
for ct in crime_types:
    resolved = await resolve_crime_sub_head(ct)
```
**Severity: High** — same class of bug as C2/H1: fixes have been applied to the local-dev/test copy of the pipeline but not the copy that's actually deployed.

### H3. OCR upload endpoint has zero size enforcement
**Files:** `backend/api/middleware/input_validator.py:39-50`, `backend/api/routes/ocr.py:11`
**Category:** Other (resource exhaustion)
**Verified-still-broken, and worse than previously described.** Codebase_Audit_v2.md's Bug #9 suggested adding a size check *inside* `ocr.py` after reading. That was never done. But independently checking the middleware's actual path-matching logic against `ocr.py`'s real route path reveals the gap is bigger than the prior report assumed: the middleware only enforces size limits when `path.endswith("/transcribe")`, `path.endswith("/upload")`, or the content-type is JSON over 2KB. The OCR route is `/api/ocr` — it matches none of these three conditions. There is currently **no size limit anywhere** (middleware or route) for image uploads to `/api/ocr`; `await image.read()` buffers the entire file into process memory unconditionally.
**Severity: High** — unbounded-memory upload endpoint with no cap at all, worse than the "add a 10MB check" fix that was proposed and never applied.

### H4. `rbac.py` is a complete no-op — the system currently has zero access control
**File:** `backend/api/middleware/rbac.py`
**Category:** Other (security)
**New finding** (implicitly known but not previously flagged as a standalone item).
```python
class RBACMiddleware:
    async def __call__(self, scope, receive, send):
        ...
        # Stub for Role-Based Access Control logic (DYSP down to Constable)
        await self.app(scope, receive, send)
```
The middleware passes every request through unconditionally. It's honestly labeled as a stub in its own comment (not a hidden facade), but it means every endpoint — including case-data query, OCR, and export — currently has no authentication or authorization check of any kind.
**Severity: High** — for a police crime-intelligence system, a transparent absence of any access control is still a meaningful exposure the moment this deploys anywhere beyond a local demo.

### H5. Fire-and-forget `asyncio.create_task` with no retained reference
**File:** `backend/job_dispatch.py:75`
**Category:** Race condition / other
**New finding.**
```python
asyncio.create_task(_local_pipeline_runner(job_id, session_id, query))
```
The returned `Task` object is never assigned or stored anywhere. This is a well-documented asyncio pitfall (the Python docs explicitly warn to "save a reference... to avoid a task disappearing mid-execution") — the task is eligible for garbage collection before it completes, which would silently drop an in-flight query with no error surfaced anywhere.
**Severity: High** — currently only reachable in the local-dev code path (`signals_url` unset), but that is exactly the path exercised by every local demo/test run described in `Rigorous_Testing_Report.md`.

### H6. SQL retrieval failures are swallowed before the confidence/synthesis layer ever sees them
**File:** `pipeline_function/pipeline/retrieval/executor.py:106-126` (`run_sql_step`)
**Category:** Other
**New finding**, compounds C6. `run_sql_step` wraps its own `ztsql_query` call in a local `try/except Exception: return []`, so the caller (`execute_with_timeout`) never observes an exception and never appends `sql_unavailable` to `evidence.confidence_caveats`. Combined with C6's schema mismatch, this means a structurally broken SQL query is permanently indistinguishable — in the reasoning trace, the confidence caveats, and the officer-facing answer — from "we checked and there's legitimately no data."
**Severity: High** — masks a real, ongoing retrieval failure as a normal empty result.

---

## 🟡 MEDIUM

### M1. TTS text length is still unbounded
**File:** `backend/api/routes/tts.py:8-10`
**Verified-still-broken.** Codebase_Audit_v2.md's Bug #8 recommended `Field(..., min_length=1, max_length=2000)` on `TTSRequest.text`. Current code: `text: str` with no `Field`/`max_length` at all. An 800-token synthesis answer forwarded whole to `/api/tts` risks the 15s Catalyst TTS timeout (per `catalyst_client.py`) or unnecessary API cost.

### M2. `sse_poller.py` still imports inside the hot polling function
**File:** `backend/sse_poller.py:13`
**Verified-still-broken.** Codebase_Audit_v2.md's Bug #7 flagged `from backend.job_dispatch import read_job_status` sitting inside `stream_job_status()`. Confirmed still present at the same location — never moved to module level.

### M3. `/api/graph` is a permanent hardcoded stub, and the prior test report misdiagnosed why
**File:** `backend/api/routes/graph.py:5-9`
```python
@router.get("/api/graph")
async def get_graph():
    # Will query Memgraph and return JSON for Cytoscape
    # For Phase 1, just a stub
    return {"nodes": [], "edges": []}
```
`Rigorous_Testing_Report.md` observed "The Network Graph container remained empty (as expected, since no mock evidence was returned by the offline graph DB)" — but this endpoint returns empty regardless of Memgraph's state; it never queries anything at all. (Note: the chat flow's own Network Graph visualization comes through the SSE `visualization` event from `langgraph_router.py`, not this endpoint — worth confirming with the team whether `/api/graph` is dead/orphaned or intended for the separate Dashboard tab's standalone use.)

### M4. Trap-scenario mock data is embedded directly in a production shared-library function
**File:** `shared/catalyst_client.py:130-152` (`kb_search`)
Honestly labeled in a comment ("Mock RAG response for the trap scenario"), but it lives in `shared/catalyst_client.py` (imported everywhere), not a test fixture. If `CATALYST_KB_URL` is ever unset in a real deployment, every real query silently gets `{"results": []}` except the two specific trap phrases, which get fabricated FIR hits — with no warning that KB search is unconfigured.

### M5. E2E smoke test cannot distinguish real answers from mock fallback text
**File:** `test_ui_playwright.py:40`
```python
assert "evidence" in last_message.lower() or "mock" in last_message.lower(), "Response missing expected mock data"
```
This assertion passes whether the pipeline returned a real evidenced answer *or* the `"[Mock Response — LLM unavailable locally]..."` fallback string. A fully broken LLM integration would still report "✅ UI E2E test passed successfully!"

### M6. `ingest_all.py` closes the Memgraph connection outside a `try/finally`
**File:** `data/scripts/ingest_all.py:85`
Unlike `ingestion/pipeline.py` and `hydrate_cloud_graph.py` (both correctly wrap `await close()` in `finally`), `ingest_all.py` calls `await close()` after the loop with no `finally`. Actual risk is low since every per-FIR write function swallows its own exceptions, but it's the same pattern Phase3_Audit_Report.md's Bug #9 fixed elsewhere and missed here.

---

## 🔵 LOW

### L1. Stale/orphaned `neo4j` dependency in `backend/requirements.txt`
No file under `backend/` imports `neo4j`/`AsyncGraphDatabase` — contradicts `Agents.md`'s explicit "backend never calls Memgraph directly" rule. Likely a leftover from before the pipeline/backend split.

### L2. `graph_definition.py`'s pipeline path is now fully dead code
**File:** `pipeline_function/pipeline/graph_definition.py`
`grep` for `run_pipeline_stages`/`get_final_state` across the repo shows no live callers anywhere (not even `test_router.py`, which now imports `run_langgraph_pipeline` from `langgraph_router.py` instead — contradicting Codebase_Audit_v2.md's claim that this file "is still used by `test_router.py`," which is now stale). The `_state_store` memory-leak fix inside it is real but exercises no live code path.

### L3. Root `package.json` is a stray leftover
**File:** `package.json`
Contains only `{"dependencies": {"cors": "^2.8.6"}}` — no name, scripts, or purpose. Nothing in the Python/Vite stack needs a root-level npm `cors` package; likely an accidental artifact from early prototyping.

### L4. `job_test_func` is a real deployed Catalyst Function target
**Files:** `functions/job_test_func/main.py`, `catalyst.json`
The function body is a "Hello from main.py" + 60-second `time.sleep` timeout-budget test — legitimate as a one-off diagnostic, but `catalyst.json`'s `functions.targets` lists it as an actual deployment target alongside the real function, consuming a deployment slot for no functional purpose.

### L5. Hardcoded developer-machine paths committed in multiple scripts
**Files:** `data/scripts/demo_ocr.py:39`, `data/scripts/validate_dataset.py:58`, `parse_html.py:3`
All three hardcode absolute paths under `/home/nkandasamy/...`, which won't exist on any other machine (including this one, which is Windows).

### L6. `pipeline_function/main.py` runs a blocking event loop as an import-time side effect
**File:** `pipeline_function/main.py:25`
`asyncio.run(warm_connections())` executes at module import time. If this module is ever imported from inside an already-running event loop (e.g. a future pytest-asyncio harness, or any code path that imports it lazily mid-request), it will raise `RuntimeError: asyncio.run() cannot be called from a running event loop`. No current caller triggers this, but it's a fragile pattern given the rest of the codebase already had one bug from mixing `asyncio.run()` with a running loop (Phase3 Bug #1).

### L7. Middleware order still runs RBAC before InputValidation
**File:** `backend/main.py:31-39`
Actual request flow (Starlette's reverse-registration-order rule, re-derived by hand): CORS → RBAC → InputValidation → route. CIS_audit_report.md's BUG-03 concern — that injection payloads would reach RBAC before sanitization — technically still applies to this ordering. Currently harmless only because RBAC (H4) is a no-op; will need re-addressing the moment RBAC is implemented.

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical | 6 |
| 🟠 High | 6 |
| 🟡 Medium | 6 |
| 🔵 Low | 7 |
| **Total** | **25** |

**The single most important thread across this audit:** this codebase has two copies of its core pipeline (`pipeline_function/main.py` + `langgraph_router.py` used for local dev/testing, vs. `functions/ps_1_cis_function/main.py` + `template_router.py` actually registered for deployment in `catalyst.json`), and essentially every round of bug-fixing across the three prior audits landed on the local-dev/test copy while the actually-deployed copy retained the original bugs (C2, H1, H2) — including the complete absence of the Confidence Engine safety check in production. Everything that has been "tested and verified" locally (`Rigorous_Testing_Report.md`, `test_chaos.py`, `verify_trap_scenario.py`) exercises the copy that isn't deployed. Combined with the mock persistence layer (C3) and the still-unchecked "Full Catalyst Deployment Verified" checklist item, there is currently no verified evidence that a real end-to-end query against the actual Zoho Catalyst deployment has ever succeeded.

No code was modified during this pass. Awaiting direction on which findings to triage first.
