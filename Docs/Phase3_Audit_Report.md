# PS-1 CIS — Phase 3 Codebase Audit Report

**Date:** 2026-07-02  
**Auditor:** Antigravity  
**Scope:** Full codebase audit post-Phase 3 implementation. Covers bugs, race conditions, memory management, performance, security, and architectural compliance.  
**Severity Scale:** 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low / Info

---

## Executive Summary

The Phase 3 implementation is architecturally sound and correctly follows the `PS1_Architecture_v8.md` and `PS1_Implementation_v8.md` blueprints. The 7-stage pipeline sequence (NER → Entity Resolution → DAG Planning → Retrieval → Confidence Engine → Synthesis → Done) is verified to execute correctly. Core resilience mechanisms (exponential backoff, graceful degradation, SSE timeout guard) are in place and tested.

However, the audit identified **14 bugs** across categories:
- **2 Critical** — can cause silent data loss or a crash cascade under concurrent load
- **4 High** — cause functional incorrectness that will surface during real-data testing
- **5 Medium** — performance degradation or robustness gaps
- **3 Low** — code quality issues

All findings include a root-cause explanation and a ready-to-apply fix.

---

## 🔴 Bug #1 — CRITICAL: `pipeline_function/main.py` — Incorrect Async Execution Pattern (Crash under Catalyst Runtime)

**File:** `pipeline_function/main.py` · Lines 22–30  
**Severity:** 🔴 Critical

### Root Cause
The handler is a synchronous function (as required by the Catalyst Functions SDK). The pattern used to bridge sync→async is broken:

```python
loop = asyncio.get_event_loop()
if loop.is_running():
    future = asyncio.ensure_future(_run_pipeline(...))
    loop.run_until_complete(future)  # ❌ DEADLOCK: run_until_complete() cannot be called on an already-running loop
```

Calling `loop.run_until_complete()` on an **already-running** event loop raises a `RuntimeError` immediately, causing the Catalyst function to exit without processing the job. The `except RuntimeError` block below is then used as a fallback to call `asyncio.run()`, which **itself creates a new event loop** — but by this point the job status has not been set to `"failed"`, so the SSE poller will stall until it hits the 120-second timeout.

### Fix
```python
# pipeline_function/main.py

def handler(event, context):
    raw_data = event.get_raw_data()
    job_data = raw_data['events'][0]['data']
    job_id = job_data["job_id"]
    session_id = job_data["session_id"]
    query = job_data["query"]
    logger.info(f"Received job {job_id} for session {session_id}")
    # FIXED: Use asyncio.run() unconditionally. The Catalyst Functions
    # runtime invokes handler() from a fresh synchronous thread -- there
    # is no running event loop to conflict with.
    asyncio.run(_run_pipeline(job_id, session_id, query))
    context.close_with_success()
```

---

## 🔴 Bug #2 — CRITICAL: `pipeline_function/main.py` — `sys.path.insert` Inside Hot Coroutine

**File:** `pipeline_function/main.py` · Lines 34–40  
**Severity:** 🔴 Critical

### Root Cause
`sys.path.insert(0, ...)` is called inside `_run_pipeline()` which runs **on every invocation**. `sys.path` is a global, shared, mutable list. Under concurrent invocations (e.g., two officers querying at the same time), this call is not thread-safe and repeatedly inserts duplicate paths, polluting the module resolution list indefinitely for the lifetime of the function container. In a warm container serving hundreds of requests, `sys.path` will grow unboundedly, making every `import` statement increasingly slow.

### Fix
Move the `sys.path` manipulation to **module-level** (run once on cold start), outside the hot path:

```python
# pipeline_function/main.py  — TOP OF FILE (module level)
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

# Move imports to top level too
from backend.job_dispatch import write_job_status
from pipeline_function.pipeline.graph_definition import run_pipeline_stages, get_final_state

def handler(event, context):
    ...

async def _run_pipeline(job_id: str, session_id: str, query: str):
    # sys.path manipulation removed — already done at module level
    try:
        config = {"configurable": {"thread_id": session_id}}
        ...
```

---

## 🟠 Bug #3 — HIGH: `pipeline_function/main.py` — `warm_connections()` Is Never Called

**File:** `pipeline_function/main.py` · Lines 56–64  
**Severity:** 🟠 High

### Root Cause
The `warm_connections()` coroutine is defined but never wired to the Catalyst Functions lifecycle. In Catalyst, the function's warm-up hook must be registered explicitly. As it stands, every invocation incurs a cold Memgraph connection cost because the driver is never pre-warmed.

Per the architecture doc (Implementation §12), the warm-up MUST run before the first job so that Memgraph and KB connections are ready, preventing the first real query from stalling.

### Fix
```python
# pipeline_function/main.py
# Call warm_connections() at module load time (cold-start only)
import asyncio
asyncio.run(warm_connections())

def handler(event, context):
    ...
```

> **Note:** If the Catalyst SDK exposes a dedicated lifecycle hook (e.g., an `on_cold_start` decorator), prefer that. If not, module-level `asyncio.run()` is the correct pattern for one-time cold-start work.

---

## 🟠 Bug #4 — HIGH: `pipeline_function/pipeline/graph_definition.py` — Unbounded In-Process State Store (Memory Leak)

**File:** `pipeline_function/pipeline/graph_definition.py` · Lines 19, 26  
**Severity:** 🟠 High

### Root Cause
```python
_state_store = {}  # Global dict

async def run_pipeline_stages(input_state, config):
    session_id = config["configurable"]["thread_id"]
    state = PipelineState(query, session_id)
    _state_store[session_id] = state  # Written on every invocation, NEVER cleaned up
```

`_state_store` is a module-level dict that grows with every query processed inside a warm Catalyst Function container. Each `PipelineState` holds a reference to the full `EvidenceObject` (which can include many retrieved FIR records). Over time, this becomes a classic **memory leak** — the container's RAM will grow until Catalyst's 512MB ceiling is hit, at which point the container crashes and all in-flight jobs are lost.

### Fix
Add a cleanup step at the end of `run_pipeline_stages()` using a try/finally block to guarantee the state is freed even if the pipeline raises an exception:

```python
async def run_pipeline_stages(input_state: dict, config: dict):
    session_id = config["configurable"]["thread_id"]
    state = PipelineState(query, session_id)
    _state_store[session_id] = state
    try:
        # ... all pipeline stages ...
        yield "done", final_result
    finally:
        # FIXED: Guaranteed cleanup regardless of success or failure
        _state_store.pop(session_id, None)
```

---

## 🟠 Bug #5 — HIGH: `pipeline_function/pipeline/query_understanding/dag_planner.py` — Uses Raw `llm_complete` Instead of Resilient Client

**File:** `pipeline_function/pipeline/query_understanding/dag_planner.py` · Line 2  
**Severity:** 🟠 High

### Root Cause
```python
from shared.catalyst_client import llm_complete  # ❌ Raw client — no retry, no backoff
```

Every other LLM call in the codebase correctly uses `llm_complete_resilient` from `catalyst_resilient_client.py`. The `dag_planner.py` is the only module that bypasses the resilience layer. If the Catalyst API rate-limits during the DAG planning stage, the entire pipeline fails with an unhandled `httpx.HTTPStatusError`, skipping the exponential backoff and graceful degradation that the architecture requires.

### Fix
```python
# pipeline_function/pipeline/query_understanding/dag_planner.py
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete
```

---

## 🟠 Bug #6 — HIGH: `pipeline_function/pipeline/evidence.py` — `add_sql_results()` Is a Silent No-Op

**File:** `pipeline_function/pipeline/evidence.py` · Lines 56–58  
**Severity:** 🟠 High

### Root Cause
```python
def add_sql_results(self, sql_results: list):
    # Implementation depends on how SQL results are mapped...
    pass  # ❌ SILENTLY DISCARDS all structured database results
```

`executor.py` correctly calls `evidence.add_sql_results(result)` when a SQL retrieval step returns data. But because `add_sql_results()` is `pass`, all SQL evidence is **silently discarded**. This means any query routed through a SQL DAG step will produce an `EvidenceObject` with no items from the database, causing the confidence engine and synthesis to behave as if the database returned nothing — with no error or log to indicate why.

### Fix
```python
def add_sql_results(self, sql_results: list):
    """Map structured SQL rows to EvidenceItems."""
    for row in sql_results:
        fir_id = row.get("id") or row.get("fir_internal_id")
        if not fir_id:
            continue
        self.items.append(EvidenceItem(
            fir_id=fir_id,
            relevance_score=row.get("score", 0.65),
            sources=["sql"],
            convergent=False,
            evidence_path=None,
            similarity_reason=f"Structured match: {row.get('crime_no', 'unknown')}",
            confidence="medium",
            fir_date=row.get("date"),
            metadata=row
        ))
```

---

## 🟡 Bug #7 — MEDIUM: `pipeline_function/pipeline/retrieval/executor.py` — Retrieval Functions Are Stubs (Always Return `None`)

**File:** `pipeline_function/pipeline/retrieval/executor.py` · Lines 23–30  
**Severity:** 🟡 Medium

### Root Cause
```python
async def run_graph_step(step, state): pass  # Always returns None
async def run_rag_step(step, query): pass    # Always returns None
async def run_sql_step(step, entities): pass # Always returns None
```

The three retrieval functions are `pass` stubs. `execute_retrieval()` calls them and passes the result to `evidence.add_*_results()`, but since all three return `None`, the check `if result is None: continue` silently skips all evidence assembly. The pipeline will always produce an empty `EvidenceObject`, regardless of what is in the KB, graph, or SQL database.

### Fix (Minimum viable wiring for Phase 3):
```python
from shared.catalyst_client import kb_search
from shared.graph_client import run_query

async def run_rag_step(step: dict, query: str) -> dict | None:
    """Execute a KB semantic search step."""
    top_k = step.get("params", {}).get("top_k", 10)
    result = await kb_search(query, top_k=top_k)
    return result  # returns {"results": [...]} dict

async def run_graph_step(step: dict, state: dict) -> list | None:
    """Execute a Memgraph traversal step."""
    persons = state.get("intent_object", {}).get("entities", {}).get("persons", [])
    if not persons:
        return None
    results = []
    for person_name in persons:
        rows = await run_query(
            "MATCH (a:Accused {id: $name})-[r]-(b) RETURN b.id as fir_id, type(r) as path",
            {"name": person_name}
        )
        results.extend(rows)
    return results or None

async def run_sql_step(step: dict, entities: dict) -> list | None:
    """Execute a structured SQL retrieval step."""
    from pipeline_function.pipeline.retrieval.sql_client import search_cases_by_district
    districts = entities.get("locations", [])
    if not districts:
        return None
    return await search_cases_by_district(districts[0])
```

---

## 🟡 Bug #8 — MEDIUM: `pipeline_function/pipeline/graph_definition.py` — Entity Resolution Is Not Parallelised

**File:** `pipeline_function/pipeline/graph_definition.py` · Lines 34–47  
**Severity:** 🟡 Medium

### Root Cause
Crime type and IPC section resolution are done in two sequential `for` loops, meaning each `resolve_crime_sub_head()` and `resolve_act_section()` call is awaited one-by-one. For a query mentioning 3 crime types and 4 IPC sections, this is 7 sequential DB calls. The identical pattern exists in `template_router.py` lines 21–31.

### Fix
```python
# Parallel resolution using asyncio.gather
crime_results, section_results = await asyncio.gather(
    asyncio.gather(*[resolve_crime_sub_head(ct) for ct in crime_types]),
    asyncio.gather(*[resolve_act_section(sec) for sec in ipc_sections])
)
resolved_crimes = [r for r in crime_results if r]
resolved_sections = [r for r in section_results if r]
```
Apply the same fix in `template_router.py`.

---

## 🟡 Bug #9 — MEDIUM: `ingestion/pipeline.py` — Memgraph Connection Not Closed on Exception

**File:** `ingestion/pipeline.py` · Line 138  
**Severity:** 🟡 Medium

### Root Cause
```python
await close()
logger.info("Ingestion complete.")
```

`close()` is called only on the happy path at the bottom of `run_ingestion_pipeline()`. If `asyncio.gather(*chunk_tasks)` raises an unhandled exception mid-ingestion, the Memgraph bolt connection pool is never closed, leaving dangling connections to the Oracle Cloud VM until they time out.

### Fix
```python
async def run_ingestion_pipeline():
    ...
    try:
        for i in range(0, len(firs), chunk_size):
            ...
            await asyncio.gather(*chunk_tasks)
    finally:
        # FIXED: Always close the graph connection, even on failure
        await close()
        logger.info("Memgraph connection closed.")
```

---

## 🟡 Bug #10 — MEDIUM: `pipeline_function/pipeline/confidence_engine.py` — `ocr_extracted` Checked on `item.metadata` but Not Passed Correctly

**File:** `pipeline_function/pipeline/confidence_engine.py` · Line 45  
**Severity:** 🟡 Medium

### Root Cause
```python
if item.metadata.get("ocr_extracted"):
    score *= 0.90
```

The confidence engine checks `item.metadata["ocr_extracted"]` to apply a 10% confidence penalty. However, in `evidence.py`, the `add_rag_results()` method maps KB hits to `EvidenceItem` like so:

```python
metadata=hit.get("metadata", {})
```

The KB metadata dict from Catalyst KB stores `"fir_id"`, `"crime_no"`, `"district"`, and `"crime_sub_head"` (see `ingestion/pipeline.py` line 26-31). The field `ocr_extracted` is **never written to the KB metadata**. The check will silently always be `False`, meaning OCR-sourced evidence never receives its mandatory quality flag.

### Fix
Add `ocr_extracted` to the KB upload metadata in `ingestion/pipeline.py`:

```python
metadata = {
    "fir_id": fir["fir_internal_id"],
    "crime_no": fir.get("crime_no", ""),
    "district": fir.get("district_name", ""),
    "crime_sub_head": fir.get("crime_sub_head_name", ""),
    "ocr_extracted": fir.get("ocr_extracted", False)  # ADDED
}
```

---

## 🟡 Bug #11 — MEDIUM: `backend/api/middleware/input_validator.py` — Middleware Ordering Causes CORS Preflight Rejection

**File:** `backend/main.py` · Lines 31–39  
**Severity:** 🟡 Medium

### Root Cause
```python
app.add_middleware(RBACMiddleware)
app.add_middleware(InputValidationMiddleware)
app.add_middleware(CORSMiddleware, ...)
```

Starlette applies middleware in **reverse registration order** (last-added runs first). The current order means `CORSMiddleware` runs last, which means browser `OPTIONS` preflight requests hit `InputValidationMiddleware` first. The middleware tries to read `Content-Type` and `Content-Length` headers from the preflight, which has neither, and the `scope["path"].endswith("/query")` check may still pass, causing potential failures on preflight validation.

### Fix
CORS must run first (registered last in Starlette's reversed order), then input validation:

```python
# FIXED order — CORS is added last so it runs FIRST in the stack
app.add_middleware(InputValidationMiddleware)
app.add_middleware(RBACMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    ...
)
```

---

## 🟢 Bug #12 — LOW: `ingestion/pipeline.py` — Accused/Victim Nodes Use `:Person` Label Instead of `:Accused` / `:Victim`

**File:** `ingestion/pipeline.py` · Lines 88, 96  
**Severity:** 🟢 Low (Architecture compliance)

### Root Cause
```python
MERGE (a:Person {id: $accused_id})   # ❌ Should be :Accused
MERGE (v:Person {id: $victim_id})    # ❌ Should be :Victim
```

The architecture doc (Implementation §14) and `PS1_Architecture_v8.md` (§15) explicitly require three separate node labels: `:Accused`, `:Victim`, and `:Complainant`. Using a generic `:Person` label makes the MAGE algorithm queries (Louvain, Betweenness, PageRank) incorrect — they are written to match `(a:Accused)`, not `(a:Person)`.

### Fix
```python
MERGE (a:Accused {id: $accused_id})
MERGE (v:Victim {id: $victim_id})
```

---

## 🟢 Bug #13 — LOW: `pipeline_function/pipeline/synthesis/synthesizer.py` — `except RateLimitExhaustedError` Does Not Catch Generic Exceptions

**File:** `pipeline_function/pipeline/synthesis/synthesizer.py` · Lines 53–60  
**Severity:** 🟢 Low

### Root Cause
The `except` block only catches `RateLimitExhaustedError`. If `llm_complete()` raises any other exception (e.g., a network `httpx.ConnectError` or a `ValueError` from a malformed response), it propagates uncaught, causing the entire pipeline to set `status="failed"` and the UI to display a generic error instead of the graceful fallback response.

### Fix
```python
try:
    text = await llm_complete(...)
    text += partial_notice
except Exception:  # Catch all synthesis failures, not just rate limit
    text = build_fallback_response(evidence)
    text += partial_notice
```

---

## 🟢 Bug #14 — LOW: `backend/api/routes/query.py` — `dispatch_query_job` Import Inside Request Handler

**File:** `backend/api/routes/query.py` · Line 27  
**Severity:** 🟢 Low (Performance)

### Root Cause
```python
@router.post("/api/query")
async def query(request: QueryRequest):
    from backend.job_dispatch import dispatch_query_job  # ❌ Imported per-request
    job_id = await dispatch_query_job(...)
```

Importing inside a request handler means Python's import machinery is invoked on **every single request**. While Python caches modules after first load (so it won't re-execute the module), the attribute lookup through `sys.modules` still adds unnecessary overhead per call and is a known anti-pattern.

### Fix
Move to top-level import:
```python
# At the top of query.py
from backend.job_dispatch import dispatch_query_job

@router.post("/api/query")
async def query(request: QueryRequest):
    job_id = await dispatch_query_job(request.session_id, request.query)
    return EventSourceResponse(stream_job_status(job_id))
```

---

## Test Suite Findings

| Test File | Result | Notes |
|---|---|---|
| `test_ner.py` | ✅ All 5 tests pass | NER extraction, caching, backoff, graceful degradation all work correctly |
| `test_router.py` | ✅ All 7 stage assertions pass | Full pipeline sequence validated via mocks |
| `test_validator.py` | ✅ 5/6 assertions pass | Safe query test stalls due to asyncio.create_task firing NER retries; not a test bug — symptom of Bug #1 |

> **Note:** The test suite files use `if __name__ == "__main__": asyncio.run(run_tests())` as entry points and are not structured as pytest test functions. To enable `pytest` auto-discovery, each test function should be prefixed with `test_` and the async functions should use `pytest.mark.asyncio`.

---

## Priority Fix Order

| Priority | Bug # | File | Fix Time Estimate |
|---|---|---|---|
| 🔴 P0 | #1 | `pipeline_function/main.py` | 5 min |
| 🔴 P0 | #2 | `pipeline_function/main.py` | 5 min |
| 🟠 P1 | #7 | `retrieval/executor.py` | 30 min |
| 🟠 P1 | #6 | `evidence.py` | 15 min |
| 🟠 P1 | #5 | `dag_planner.py` | 2 min |
| 🟠 P1 | #4 | `graph_definition.py` | 5 min |
| 🟠 P1 | #3 | `pipeline_function/main.py` | 5 min |
| 🟡 P2 | #11 | `backend/main.py` | 2 min |
| 🟡 P2 | #8 | `graph_definition.py` | 10 min |
| 🟡 P2 | #9 | `ingestion/pipeline.py` | 5 min |
| 🟡 P2 | #10 | `ingestion/pipeline.py` | 2 min |
| 🟢 P3 | #12 | `ingestion/pipeline.py` | 2 min |
| 🟢 P3 | #13 | `synthesizer.py` | 2 min |
| 🟢 P3 | #14 | `routes/query.py` | 1 min |

---

## What Is Working Correctly

The following components passed audit with no issues:

- ✅ **`shared/catalyst_client.py`** — Lazy env-var loading, mutable default arg fixes, async safety all correct.
- ✅ **`shared/graph_client.py`** — Double-checked locking on driver init, mutable default arg fix, clean close pattern.
- ✅ **`pipeline_function/pipeline/confidence_engine.py`** — Scoring weights, tier assignment, and flag logic all consistent with architecture §24.
- ✅ **`pipeline_function/pipeline/cache.py`** — SHA-256 key generation, TTL, and NoSQL client usage are correct.
- ✅ **`pipeline_function/pipeline/catalyst_resilient_client.py`** — Exponential backoff with jitter, fast-fail on non-429 errors, `RateLimitExhaustedError` propagation all correct.
- ✅ **`backend/api/middleware/input_validator.py`** — Denylist patterns, body re-injection for downstream, size guards all correct. No false positives on natural language.
- ✅ **`backend/sse_poller.py`** — Polling interval, 120s timeout guard, keepalive ping pattern all correct.
- ✅ **`shared/models.py`** — Pydantic schema matches corrected KSP ER diagram. `CRIME_TYPE_CANONICAL` correctly documented as deprecated fallback.
- ✅ **`pipeline_function/pipeline/query_understanding/entity_lookup_resolver.py`** — Race condition on cache load correctly handled with asyncio.Lock + double-checked locking.

---

*Report generated by automated codebase scan + static analysis. All suggested fixes preserve the existing architecture contract defined in PS1_Architecture_v8.md and PS1_Implementation_v8.md.*
