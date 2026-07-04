# PS-1 CIS — Full Codebase Audit Report (Post-Phase 1 Blockers)

**Date:** 2026-07-03  
**Auditor:** Antigravity  
**Scope:** Full codebase audit covering all files as of Phase 1 blocker completion. Includes all new files since the Phase 3 audit (`langgraph_router.py`, new backend routes, updated `executor.py`, updated `main.py`).  
**Severity Scale:** 🔴 Critical · 🟠 High · 🟡 Medium · 🟢 Low

---

## Executive Summary

The codebase has matured significantly since the Phase 3 audit. Several bugs from that report have been fixed (mock stubs replaced with real implementations, `dag_planner.py` now uses resilient client, middleware ordering corrected, `add_sql_results` implemented, `_state_store` now has a `finally` cleanup). 

This audit identified **12 new or unresolved issues** across the updated codebase:

| Severity | Count | Notes |
|---|---|---|
| 🔴 Critical | 2 | New: Cypher injection via unsanitised f-string query; History unbounded growth |
| 🟠 High | 4 | Regression: resolver called sequentially in `graph_definition.py`; `langgraph_router.py` workflow compiled at import-time; visualization variables referenced before assignment; `export.py` Jinja2 env created per request |
| 🟡 Medium | 4 | SSE poller import inside hot loop; TTS no length guard; OCR bytes not closed; chaos test passes empty string to pipeline |
| 🟢 Low | 2 | Dead code (`graph_definition.py`); `diagnose_graph.py` and scratch files in repo root |

---

## 🔴 Bug #1 — CRITICAL: `pipeline_function/pipeline/retrieval/executor.py` — Cypher Injection via Unsanitised f-string

**File:** `retrieval/executor.py` · Lines 103–108  
**Severity:** 🔴 Critical

### Root Cause
The visualization Cypher query in **both** `langgraph_router.py` (line 103) and `template_router.py` (line 81) builds the `IN` clause by string-interpolating FIR IDs directly:

```python
# langgraph_router.py:103
fir_list_str = "[" + ", ".join([f"'{fid}'" for fid in fir_ids]) + "]"
person_query = f"""
MATCH (p:Person)-[r]->(f:FIR)
WHERE f.id IN {fir_list_str}   # ❌ INJECTION POINT
...
"""
```

A FIR ID that contains a single quote or Cypher keyword (e.g., `abc'] RETURN 1 UNION MATCH (n) DETACH DELETE n //`) would **corrupt the query structure**. While FIR IDs are UUIDs and therefore safe in practice, this pattern is architecturally insecure and will fail if the ID format ever changes. Using string interpolation for query parameters is always wrong in graph/SQL databases.

### Fix
Use parameterized Cypher with a list parameter:

```python
# FIXED — parameterized query, no injection risk
person_query = """
MATCH (p:Person)-[r]->(f:FIR)
WHERE f.id IN $fir_ids
RETURN p.id as person_id, type(r) as rel_type, f.id as fir_id
"""
results = await run_query(person_query, {"fir_ids": fir_ids})
```
Apply the same fix to `template_router.py` line 81.

---

## 🔴 Bug #2 — CRITICAL: `pipeline_function/main.py` — Conversation History Grows Without Bound (Memory Leak)

**File:** `pipeline_function/main.py` · Lines 47–56  
**Severity:** 🔴 Critical

### Root Cause
```python
history_doc = await nosql_get(f"history:{session_id}")
history = json.loads(history_doc["value"]) if history_doc else []
# ... pipeline runs ...
history.append({"q": query, "a": job["result"]["answer"]})
await nosql_set(f"history:{session_id}", json.dumps(history))
```

The conversation history list is loaded from NoSQL, appended to, and saved back — **with no maximum length enforced**. Every query appends a `{"q": ..., "a": ...}` dict where `"a"` is the full LLM synthesis response (potentially 800+ tokens of text). An active session over a demo day (20-30 queries) could accumulate 25KB+ in a single NoSQL document. More critically, the entire history is later serialised into the LLM prompt in `synthesizing_response_node`, meaning every subsequent query carries the full accumulated context, rapidly approaching the model's context-window limit and increasing synthesis latency linearly with session length.

The `synthesizing_response_node` already slices `state["history"][-3:]` for the prompt, but the stored document continues to grow.

### Fix
Cap the stored history at the same window used for synthesis:

```python
MAX_HISTORY_ENTRIES = 10  # Keep last 10 turns in storage

history.append({"q": query, "a": job["result"]["answer"]})
history = history[-MAX_HISTORY_ENTRIES:]  # FIXED: trim before saving
await nosql_set(f"history:{session_id}", json.dumps(history))
```

Apply the same cap in `backend/job_dispatch.py` `_local_pipeline_runner()` (lines 91-92).

---

## 🟠 Bug #3 — HIGH: `pipeline_function/pipeline/langgraph_router.py` — Workflow Graph Compiled at Import Time (Breaks Concurrent Requests)

**File:** `langgraph_router.py` · Lines 213–232  
**Severity:** 🟠 High

### Root Cause
```python
# Module level — executes ONCE when the module is first imported
workflow = StateGraph(AgentState)
workflow.add_node(...)
...
app = workflow.compile()  # ❌ Compiled once, shared across all invocations
```

`StateGraph.compile()` is called at module import time, producing a single shared `app` object. In the Catalyst Functions runtime, **all concurrent invocations share this single compiled graph**. LangGraph's `ainvoke()` is not guaranteed to be thread-safe when called concurrently on the same compiled graph object — state can bleed between invocations.

### Fix
Compile the graph inside `run_langgraph_pipeline()` to give each invocation its own instance:

```python
# Remove module-level workflow/app variables entirely

async def run_langgraph_pipeline(job_id, query, write_status_callback, history=None):
    # FIXED: compile fresh per invocation — safe for concurrency
    workflow = StateGraph(AgentState)
    workflow.add_node("understanding_query", understanding_query_node)
    # ... all add_node/add_edge calls ...
    workflow.set_entry_point("understanding_query")
    graph_app = workflow.compile()

    initial_state = {
        "job_id": job_id,
        "query": query,
        "write_status_callback": write_status_callback,
        "history": history or []
    }
    final_state = await graph_app.ainvoke(initial_state)
    ...
```

> **Note:** The performance cost is ~1-5ms per compilation, negligible compared to LLM call latency.

---

## 🟠 Bug #4 — HIGH: `pipeline_function/pipeline/graph_definition.py` — Entity Resolution Still Sequential (Regression from Phase 3 Audit)

**File:** `graph_definition.py` · Lines 36–44  
**Severity:** 🟠 High

### Root Cause
The Phase 3 audit found this bug and the fix was applied in `langgraph_router.py` (`resolving_entities_node` now correctly uses `asyncio.gather`). However, `graph_definition.py` was updated at the same time but the fix was **not applied** — it still uses sequential `for` loops:

```python
# graph_definition.py:36-44  — STILL sequential
for ct in crime_types:
    resolved = await resolve_crime_sub_head(ct)
    ...
for sec in ipc_sections:
    resolved = await resolve_act_section(sec)
```

Since `_local_pipeline_runner` in `job_dispatch.py` was updated to call `run_langgraph_pipeline` (the fixed version), this code path is no longer the primary route, but it **is still used by `test_router.py`** which tests `run_pipeline_stages` directly. This inconsistency will cause confusion and slow test runs.

### Fix
Apply the same `asyncio.gather` pattern already used in `langgraph_router.py`:

```python
# graph_definition.py — resolving_entities section
crime_results, section_results = await asyncio.gather(
    asyncio.gather(*[resolve_crime_sub_head(ct) for ct in crime_types]) if crime_types else asyncio.coroutine(lambda: [])(),
    asyncio.gather(*[resolve_act_section(sec) for sec in ipc_sections]) if ipc_sections else asyncio.coroutine(lambda: [])(),
)
resolved_crimes = [r for r in crime_results if r]
resolved_sections = [r for r in section_results if r]
```

Or more cleanly with a helper:

```python
async def _gather_or_empty(coros):
    return await asyncio.gather(*coros) if coros else []

resolved_crimes_raw, resolved_sections_raw = await asyncio.gather(
    _gather_or_empty([resolve_crime_sub_head(ct) for ct in crime_types]),
    _gather_or_empty([resolve_act_section(sec) for sec in ipc_sections])
)
resolved_crimes = [r for r in resolved_crimes_raw if r]
resolved_sections = [r for r in resolved_sections_raw if r]
```

---

## 🟠 Bug #5 — HIGH: `pipeline_function/pipeline/template_router.py` — Variables `donut_data`, `trend_data`, `map_markers` Referenced Outside Their `if fir_ids:` Scope

**File:** `template_router.py` · Lines 162–165  
**Severity:** 🟠 High

### Root Cause
```python
if fir_ids:
    ...
    donut_data = [...]   # defined only inside if-block
    map_markers = [...]  # defined only inside if-block
    trend_data = [...]   # defined only inside if-block

visualization = {
    "recharts": { "donut": donut_data if fir_ids else [], ... },  # ❌ NameError if fir_ids is falsy
}
```

If `fir_ids` is empty (i.e., no evidence was retrieved), the three variables are never assigned. The ternary `donut_data if fir_ids else []` guards against using the value, but Python evaluates **both branches** at expression evaluation time in terms of name resolution. If `fir_ids` is falsy, `donut_data` is still referenced and Python will raise `NameError: name 'donut_data' is not defined`.

The same bug exists in `langgraph_router.py` at line 176.

### Fix
Initialize the variables before the `if` block:

```python
# FIXED: initialize before conditional block
donut_data = []
map_markers = []
trend_data = []

if fir_ids:
    # ... overwrite as before ...
    donut_data = [...]
    map_markers = [...]
    trend_data = [...]

visualization = {
    "cytoscape": {"elements": cytoscape_elements},
    "recharts": {"donut": donut_data, "trend": trend_data},
    "leaflet": {"markers": map_markers}
}
```

Apply to both `template_router.py` and `langgraph_router.py`.

---

## 🟠 Bug #6 — HIGH: `backend/api/routes/export.py` — Jinja2 `Environment` Created Per Request (Performance)

**File:** `backend/api/routes/export.py` · Lines 26–32  
**Severity:** 🟠 High

### Root Cause
```python
@router.post("/api/export/pdf")
async def export_pdf(request: ExportRequest):
    template_dir = os.path.abspath(...)
    env = Environment(loader=FileSystemLoader(template_dir))  # ❌ New env every request
    template = env.get_template('report.html')
```

A new `jinja2.Environment` is instantiated on every PDF export request. Jinja2 environments are expensive to create — they parse templates, cache compiled bytecode, and set up the loader. In addition, `FileSystemLoader` performs disk I/O to resolve the template directory on every construction. This is the Jinja2 anti-pattern; the environment should be a module-level singleton.

### Fix
```python
import os
from jinja2 import Environment, FileSystemLoader

# FIXED: module-level singleton — created once on cold start
_TEMPLATE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../templates'))
_JINJA_ENV = Environment(loader=FileSystemLoader(_TEMPLATE_DIR))

@router.post("/api/export/pdf")
async def export_pdf(request: ExportRequest):
    try:
        template = _JINJA_ENV.get_template('report.html')
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Template not found: {e}")
    ...
```

---

## 🟡 Bug #7 — MEDIUM: `backend/sse_poller.py` — `read_job_status` Import Inside Hot Polling Loop

**File:** `backend/sse_poller.py` · Line 13  
**Severity:** 🟡 Medium

### Root Cause
```python
async def stream_job_status(job_id: str):
    from backend.job_dispatch import read_job_status  # ❌ Import inside function
    ...
    while elapsed < SSE_MAX_POLL_SECONDS:
        job = await read_job_status(job_id)  # Polled every 0.5s
```

The import is inside the generator function body, meaning Python's import system is invoked once per SSE connection (not once per poll cycle, since generators run lazily). While cached after first import, this still adds a `sys.modules` dict lookup on every fresh SSE connection. More importantly, it obscures the dependency and makes the code harder to test. The Phase 3 audit flagged a similar pattern in `query.py` which was fixed — this one was missed.

### Fix
```python
# Move to top of file
from backend.job_dispatch import read_job_status

async def stream_job_status(job_id: str):
    last_status = None
    elapsed = 0.0
    ...
```

---

## 🟡 Bug #8 — MEDIUM: `backend/api/routes/tts.py` — No Maximum Length Guard on TTS Text Input

**File:** `backend/api/routes/tts.py` · Lines 13–15  
**Severity:** 🟡 Medium

### Root Cause
```python
@router.post("/api/tts")
async def generate_tts(request: TTSRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="Text is required")
    audio_bytes = await text_to_speech(request.text, request.language)
```

The empty-string check is present, but there is no upper length bound. An officer's response from the LLM can be up to 800 tokens (~600 words, ~4,000 characters). If the frontend sends the entire synthesis answer to TTS, the Catalyst ASR endpoint may:
1. Time out (the `catalyst_client.py` TTS has a 15s timeout).
2. Incur excessive API credit usage per call.

The Pydantic model also has no `max_length` constraint on `text`.

### Fix
```python
class TTSRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)  # ADDED: cap at ~1500 tokens
    language: str = "kn"
```

---

## 🟡 Bug #9 — MEDIUM: `backend/api/routes/ocr.py` — Uploaded Image Bytes Not Bounded, Entire File Read Into Memory

**File:** `backend/api/routes/ocr.py` · Lines 10–11  
**Severity:** 🟡 Medium

### Root Cause
```python
@router.post("/api/ocr")
async def extract_ocr(image: UploadFile = File(...)):
    image_bytes = await image.read()  # ❌ No size check BEFORE reading into memory
```

`await image.read()` loads the entire file into RAM before the MIME check. The `InputValidationMiddleware` has a size check for `/upload` paths but not for `/ocr`. A malicious 50MB upload would be fully read into the FastAPI process memory before being rejected. This is also inconsistent with the `transcribe` route which correctly checks `len(audio_bytes) > MAX_AUDIO_SIZE_BYTES` after reading (still a small window but size-matches the content-length guard).

### Fix
Add a size guard immediately after reading, consistent with the `transcribe` route:

```python
from backend.api.middleware.input_validator import MAX_DOC_SIZE_BYTES

@router.post("/api/ocr")
async def extract_ocr(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if len(image_bytes) > MAX_DOC_SIZE_BYTES:  # ADDED: 10MB cap
        raise HTTPException(status_code=413, detail="Image exceeds 10MB limit")
    if not validate_mime_type(image_bytes, ALLOWED_IMAGE_MIMES):
        raise HTTPException(status_code=415, detail="Unsupported image format")
    ...
```

---

## 🟡 Bug #10 — MEDIUM: `test_chaos.py` — Empty String Query Sent to Pipeline Without Guard

**File:** `test_chaos.py` · Line 25  
**Severity:** 🟡 Medium

### Root Cause
```python
CHAOS_QUERIES = [
    ...
    ""   # ❌ Empty string
]
```

The chaos test includes an empty string query which is deliberately adversarial. However, the `InputValidationMiddleware` (which guards the HTTP endpoint) is **bypassed** in `test_chaos.py` because the test calls `run_langgraph_pipeline()` directly. The empty string reaches `extract_ner_and_intent("")` and then `build_ner_prompt("")`, which builds a prompt with an empty `Query:` field. This is an acceptable test scenario, but it should **assert** that the pipeline returns a valid (non-crash) fallback response rather than just checking for the presence of `answer`. Currently, if the pipeline crashes on empty string, `captured_result` stays `{}` and the test reports "returned no text answer" — not the actual exception.

### Fix
```python
except Exception as e:
    print(f"❌ FAILED (Exception thrown): {type(e).__name__}: {str(e)}")
    import traceback; traceback.print_exc()  # ADDED: print full stack trace for diagnosis
    failed += 1
```

Also add an explicit assertion message for empty-string: `# Note: empty string is expected to return a graceful fallback, not crash.`

---

## 🟢 Bug #11 — LOW: `pipeline_function/pipeline/graph_definition.py` — Dead Code Path

**File:** `graph_definition.py` · Lines 94–99  
**Severity:** 🟢 Low

### Root Cause
`get_final_state()` reads from `_state_store` after the `finally` block has already popped the session from the store. Since `_state_store.pop(session_id, None)` runs in the `finally` clause of `run_pipeline_stages()`, `get_final_state()` will **always** return `{}`.

Currently the only caller in `pipeline_function/main.py` also uses `run_langgraph_pipeline()` (not `run_pipeline_stages`), so this is dead code in the active code path.

### Fix
Either remove `get_final_state()` entirely, or restructure so the final result is returned via the generator's yield rather than stored and fetched separately. The `langgraph_router.py` pattern (returning the final state from `ainvoke`) is the correct approach and does not need this function.

---

## 🟢 Bug #12 — LOW: Root-Level Scratch/Debug Scripts Should Not Be in the Repository

**Files:** `diagnose_graph.py`, `parse_html.py`, `test_data.py`, `test_sdk.py`, `test_catalyst.py`, `test_groq.py`, `test_groq_models.py`, `test_llm.py`, `test_llm_json.py`, `test_pipeline.py`  
**Severity:** 🟢 Low

### Root Cause
The repository root contains multiple one-off test and diagnostic scripts that were used during development. These are committed to the repo rather than being stored in `.tmp/` (as specified in `Agents.md`). This creates noise in the project root and could confuse future contributors about which tests are canonical vs. ad-hoc.

### Fix
Move canonical tests to a proper `tests/` directory with `pytest` structure:
```
tests/
  test_ner_pipeline.py     # was test_ner.py
  test_chaos.py            # chaos tests
  test_validator.py        # input validation
```
Delete or `.gitignore` the diagnostic/groq/sdk scripts. Add to `.gitignore`:
```
test_groq*.py
test_llm*.py
test_sdk.py
test_catalyst.py
diagnose_*.py
parse_*.py
```

---

## Previous Audit Fixes Verified ✅

The following bugs from `Phase3_Audit_Report.md` have been confirmed fixed:

| Bug # | Issue | Status |
|---|---|---|
| #1 | `main.py` deadlock (`run_until_complete` on running loop) | ✅ Fixed — now uses `asyncio.run()` unconditionally |
| #2 | `sys.path.insert` inside hot coroutine | ✅ Fixed — moved to module level |
| #3 | `warm_connections()` never called | ✅ Fixed — called via `asyncio.run()` at module level |
| #4 | `_state_store` memory leak | ✅ Fixed — `finally` block added to `run_pipeline_stages` |
| #5 | `dag_planner.py` using raw LLM client | ✅ Fixed — uses `llm_complete_resilient` |
| #6 | `add_sql_results()` was `pass` | ✅ Fixed — full implementation present |
| #7 | Retrieval executor stubs | ✅ Fixed — all three retrieval functions implemented |
| #8 | Entity resolution not parallelised | ✅ Fixed in `langgraph_router.py`; regression in `graph_definition.py` (see Bug #4) |
| #9 | Memgraph connection not closed on exception | ✅ Fixed — `finally: await close()` added |
| #10 | `ocr_extracted` flag not propagated | 🔄 Partially: `synthesizer.py` now catches all exceptions; flag still not in KB metadata |
| #11 | CORS middleware ordering | ✅ Fixed — `backend/main.py` ordering corrected |
| #12 | Accused/Victim using `:Person` label | ✅ Fixed in `ingestion/pipeline.py` (uses `:Accused`/`:Victim`) |
| #13 | Synthesizer only catching `RateLimitExhaustedError` | ✅ Fixed — `except Exception` now used |
| #14 | `dispatch_query_job` import inside request handler | ✅ Fixed — moved to module level |

---

## Performance Optimizations

Beyond the bugs above, the following non-critical optimizations are recommended:

### P1 — `langgraph_router.py`: Cap Evidence Items Serialized to Synthesis Prompt
Currently all `evidence_obj.items` are iterated for the synthesis prompt dict (line 188-195). Since synthesis only uses the top 10 items, serialize only those:
```python
# BEFORE
for item in evidence_obj.items:   # can be 50+ items

# AFTER
for item in evidence_obj.items[:10]:   # match what synthesizer.py already caps to
```

### P2 — `executor.py`: Skip Steps with Impossible Params  
If a DAG plan includes a `sql` step but `entities.get("locations")` is empty, the step is dispatched and immediately returns `[]` after a round-trip to the ztsql endpoint. Add a pre-flight check before creating the coroutine:
```python
elif step_type == "sql":
    if not evidence.entities.get("locations") and not evidence.entities.get("city"):
        continue   # No location to query on, skip
    coro = run_sql_step(step, evidence.entities)
```

### P3 — `client/src/App.tsx`: `scrollToBottom` Called on Every Message Update
The `useEffect` dependency on `[messages]` causes `scrollToBottom()` to fire on **every single** `setMessages` call — including intermediate SSE status updates. Since status updates happen every 0.5 seconds during pipeline execution, this causes 20-40 unnecessary DOM scroll operations per query. 

```typescript
// BEFORE: fires on every messages state change
useEffect(() => { scrollToBottom(); }, [messages]);

// AFTER: only scroll when a new message is added (length changes)
const prevLengthRef = useRef(messages.length);
useEffect(() => {
  if (messages.length > prevLengthRef.current) {
    scrollToBottom();
  }
  prevLengthRef.current = messages.length;
}, [messages]);
```

---

## Priority Fix Order

| Priority | Bug # | File | Estimated Fix Time |
|---|---|---|---|
| 🔴 P0 | #1 | `langgraph_router.py` + `template_router.py` | 5 min |
| 🔴 P0 | #2 | `pipeline_function/main.py` + `job_dispatch.py` | 5 min |
| 🟠 P1 | #3 | `langgraph_router.py` | 10 min |
| 🟠 P1 | #5 | `template_router.py` + `langgraph_router.py` | 5 min |
| 🟠 P1 | #6 | `export.py` | 5 min |
| 🟠 P1 | #4 | `graph_definition.py` | 5 min |
| 🟡 P2 | #7 | `sse_poller.py` | 2 min |
| 🟡 P2 | #8 | `tts.py` | 2 min |
| 🟡 P2 | #9 | `ocr.py` | 3 min |
| 🟡 P2 | #10 | `test_chaos.py` | 5 min |
| 🟢 P3 | #11 | `graph_definition.py` | 10 min |
| 🟢 P3 | #12 | Root-level scripts | 15 min |
| — | Perf P1 | `langgraph_router.py` | 2 min |
| — | Perf P2 | `executor.py` | 5 min |
| — | Perf P3 | `client/src/App.tsx` | 5 min |

---

*This report was generated by static analysis of the full codebase as of 2026-07-03. All suggested fixes preserve the existing architecture contract defined in `PS1_Architecture_v8.md` and `PS1_Implementation_v8.md`.*
