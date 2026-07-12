# PS-1 Production Remediation & Debugging Report
**Date:** 2026-07-12
**System:** PS-1 Conversational Crime Intelligence System
**Environment:** Zoho Catalyst (AppSail + Serverless Event Functions) + Memgraph (AWS EC2 / OCI)

## Executive Summary
This document serves as a comprehensive post-mortem and reference guide for the stabilization of the PS-1 production pipeline. It details the transition from a local/mock development environment to a fully distributed, event-driven serverless architecture on Zoho Catalyst. The debugging process uncovered critical nuances in serverless event loop lifecycles, silent fallback masking, and event payload serialization.

---

## 1. Signal Handoff & Dispatch Routing Failures

### **Symptom**
The AppSail backend failed to dispatch queries to the background processing function. The backend logs showed `404 Not Found` when attempting to publish to the Catalyst Signals bus, alongside spurious `405 Method Not Allowed` errors for `/health`.

### **Diagnosis**
1. **Red Herring (`405 /health`):** The 405 error was an automated health-check probe from Catalyst's AppSail ingress gateway pinging the FastAPI container. It had no impact on the pipeline.
2. **Signal Webhook Formatting:** The `ZC_SIGNALS_PUBLISHER_URL` environment variable was incorrectly configured. It was pointing to an internal BaaS endpoint instead of the explicitly required Signals V2 webhook URL containing the cryptographic `digest` parameter.

### **Fix Implemented**
*   Retrieved the correct webhook URL (`https://api.catalyst.zoho.in/signals/v2/event_notification?digest=...`) directly from the Catalyst Signals console.
*   Updated the AppSail environment variables and triggered a clean container redeploy to flush the stale environment cache.

---

## 2. Event Payload Parsing Crashes

### **Symptom**
Once the Signal dispatch succeeded, the serverless function (`ps_1_cis_function`) immediately crashed upon invocation, throwing `TypeError: string indices must be integers` or `KeyError: 'job_id'` in the logs.

### **Diagnosis**
The `backend/job_dispatch.py` module serialized the job data payload as a JSON string before pushing it to the Signals bus. However, Catalyst Signals wraps incoming payloads inside a nested `events` array and a `data` key. The serverless handler attempted to access `raw_event_data["job_id"]` directly, failing because `raw_event_data` was a stringified JSON object, not a parsed Python dictionary.

### **Fix Implemented**
*   Rewrote the payload extraction logic in `ps_1_cis_function/main.py`.
*   Added explicit type-checking and `json.loads(raw_event_data)` to safely unwrap the stringified payload before attempting dictionary traversal.

---

## 3. Silent Fallback Masking & The "QUEUED..." UI Hang

### **Symptom**
The frontend UI hung indefinitely in the `QUEUED...` state with the skeleton loaders spinning. However, the serverless function logs proudly declared: `[DIAG][HANDLER] ✅ Pipeline complete for job <UUID>`.

### **Diagnosis**
This was the most deceptive bug of the deployment, involving a chain of silent failures:
1. **Environment Variable Injection:** Catalyst functions inject environment variables *after* module import. Initial diagnostic prints (`[DIAG][ENV]`) checked the environment at import time, falsely reporting that all variables were `NOT SET`.
2. **Missing Configuration:** The variables `ZC_PROJECT_ID` and `ZC_LLM_ENDPOINT` were genuinely missing from the function's configuration in the Catalyst UI.
3. **The Silent Mock Fallback:** In `shared/catalyst_client.py`, the `nosql_set()` and `nosql_get()` methods had a safety fallback: if `project_id` or auth credentials were not found, they silently reverted to reading/writing to a local `.nosql_mock_db.json` file.
4. **The Divergence:** 
    *   The **AppSail Backend** (which had the Project ID) wrote `status="queued"` to the **Real Catalyst NoSQL table**.
    *   The **Serverless Function** (missing the Project ID) executed the pipeline, failed the LLM calls (due to missing `ZC_LLM_ENDPOINT`), triggered the LangGraph synthesis fallback, and wrote `status="done"` to the **temporary mock DB inside its ephemeral container**.
    *   The frontend SSE poller continued querying the Real NoSQL table, which remained permanently `"queued"`.

### **Fix Implemented**
*   Identified the exact missing variables required by the SDK.
*   Added `ZC_PROJECT_ID` and `ZC_LLM_ENDPOINT` directly to the `Development` environment of the Catalyst Function via the UI.
*   **Crucial CLI Fix:** Edited `functions/ps_1_cis_function/catalyst-config.json` to remove the `"env_variables": {}` block. This prevented the `catalyst deploy` CLI command from syncing an empty object to the cloud and wiping out the manually configured UI variables.

---

## 4. Serverless Asyncio Event Loop Crashes (Neo4j / Memgraph)

### **Symptom**
With auth restored, the pipeline successfully executed but the LLM consistently returned the fallback message: *"Analysis engine temporarily unavailable... Task pending attached to a different loop"*.

### **Diagnosis**
This is a classic concurrency bug specific to Python serverless environments:
1. Catalyst spins up a background container and creates an `asyncio` event loop per invocation via `asyncio.run()`.
2. Our `shared/graph_client.py` maintained a **global** Neo4j driver connection cache (`_driver = AsyncGraphDatabase.driver(...)`).
3. The Python `neo4j` driver natively spawns background tasks (like connection pool keepalives) that bind strictly to the active event loop.
4. When the serverless invocation ended, Catalyst destroyed the event loop. Upon the *next* invocation, a brand new event loop was created.
5. The global `_driver` survived in memory, but its internal background tasks were still tied to the destroyed loop. Any attempt to use `driver.session()` instantly crashed with: `RuntimeError: Task attached to a different loop`.

### **Fix Implemented**
*   Modified `shared/graph_client.py` to entirely **disable global driver caching** in the serverless deployment.
*   Updated `get_driver()` to instantiate a brand new `AsyncGraphDatabase.driver` on every single execution.
*   Implemented strict `try...finally` blocks wrapping `await driver.close()` around every query execution to guarantee that the driver and its associated background tasks are cleanly torn down before the serverless container destroys the event loop.

---

## Final Validation
Following the application of the above fixes, the system successfully parsed a complex semantic query (*"Are there any robbery gangs from Mangaluru using glass cutters?"*). 

The LLM seamlessly parsed the empty dataset correctly, and upon subsequent testing with valid parameters (*"highway blocking"*), retrieved accurate graph nodes, executed the `Synthesis` node, and rendered a highly accurate tactical report to the frontend UI with dynamic citations and confidence scoring intact.

The PS-1 pipeline is officially stable and production-ready.
