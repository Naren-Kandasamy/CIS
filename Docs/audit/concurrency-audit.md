# PS-1 CIS — Concurrency & Load Audit

**Date:** 2026-07-04
**Auditor:** Claude (Sonnet 5), audit-only pass — no code modified
**Scope:** Not per-file bugs (`audit-report.md`) or cross-module contract mismatches (`cascading-logic-audit.md`). This pass asks specifically: what breaks under *real simultaneous traffic* — overlapping requests, duplicate event delivery, concurrent reads during writes — that a single manual test run would never surface. Every finding was verified by reading the exact current code and reasoning through the actual `asyncio` suspension points, not just spotting a shared mutable variable.

---

## 🔴 CRITICAL

### 1. Same-session concurrent queries silently lose conversation history (lost-update race)
**Files:** `backend/job_dispatch.py::_local_pipeline_runner` (lines ~79-99), `pipeline_function/main.py::_run_pipeline` (lines ~44-61) — identical pattern in both

```python
history_doc = await nosql_get(f"history:{session_id}")
history = json.loads(history_doc["value"]) if history_doc else []
await run_langgraph_pipeline(job_id, query, write_job_status, history)   # long-running: multiple LLM calls, retries
job = await read_job_status(job_id)
if job and job.get("status") == "done":
    history.append({"q": query, "a": job["result"]["answer"]})
    history = history[-10:]
    await nosql_set(f"history:{session_id}", json.dumps(history))
```
This is a textbook read-modify-write race with no lock, and the window between read and write is not a few milliseconds — it spans the *entire pipeline run* (NER extraction, entity resolution, retrieval, confidence scoring, synthesis: several real network/LLM calls, each with up to 3 retries on rate-limit). If two queries for the same `session_id` are in flight concurrently:
- Query A reads history = `[...N items]`, starts its multi-second pipeline run.
- Before A finishes, Query B (same session) also reads history = `[...N items]` — unaware A will add anything.
- Whichever of A/B finishes last overwrites `history:{session_id}` with its own snapshot + its own new turn, **silently discarding the other query's contribution** to the conversation history entirely. No error, no log, no indication to either request that this happened.

**What actually gates this today:** the frontend disables the query input while `isLoading` is true (`client/src/App.tsx`), which prevents *one tab* from firing two overlapping submits through the UI. But `sessionStorage` (where `SESSION_ID` lives) is per-tab in most browsers **except** it is commonly copied forward when a tab is duplicated (browser "duplicate tab" / some `window.open` scenarios) — a very plausible real action for an officer working the same case in two windows side-by-side. Nothing server-side enforces per-session serialization; the guard is purely a client-side UI affordance, not a backend guarantee.
**Severity: Critical** — silent, undetectable loss of conversation context is exactly the kind of bug that looks fine in every manual single-request test and only appears under real multi-tab usage, which is a normal (not exotic) way to use a chat app.

### 2. No idempotency guard on job/event processing — a duplicate Signals delivery re-runs the whole pipeline and double-charges Catalyst credits
**Files:** `functions/ps_1_cis_function/main.py::handler`, `pipeline_function/main.py::handler`

```python
def handler(event, context):
    raw_data = event.get_raw_data()
    job_data = raw_data['events'][0]['data']
    job_id = job_data["job_id"]
    ...
    asyncio.run(_run_pipeline(job_id, session_id, query))
    context.close_with_success()
```
There is no check anywhere ("has `job_id` already been processed / is it already in progress?") before running the full pipeline. Pub-sub/webhook systems like Zoho Catalyst Signals commonly use at-least-once delivery — if `context.close_with_success()` isn't called in time on a first attempt (a slow LLM retry chain is exactly the kind of thing that could cause this), a redelivery of the *same* event would run the *entire* pipeline a second time for the same `job_id`: a second full round of LLM calls (NER + DAG planning + synthesis), a second Memgraph query round-trip, and — per finding 1 above — a second, separately-computed append to the same session's conversation history (the same question answered twice, potentially with different wording since synthesis temperature > 0, both landing in history).
**Severity: Critical**, specifically *because* `Agents.md` §3 explicitly flags Catalyst credits as "hackathon-finite" and rate-limit stalls as expensive in wall-clock time — an idempotency gap here isn't just a correctness nit, it directly threatens the resource budget the team has already identified as scarce.

---

## 🟠 HIGH

### 3. NER cache has no in-flight lock — concurrent identical queries stampede the LLM
**Files:** `pipeline_function/pipeline/cache.py`, `pipeline_function/pipeline/query_understanding/ner_intent.py::extract_ner_and_intent`, contrast with `pipeline_function/pipeline/query_understanding/entity_lookup_resolver.py::_load_caches_if_needed`

```python
async def extract_ner_and_intent(normalized_query: str) -> dict:
    cached = await get_cached_ner(normalized_query)
    if cached:
        return cached
    prompt = build_ner_prompt(normalized_query)
    raw = await llm_complete(prompt=prompt, system=NER_INTENT_SYSTEM, ...)   # <- real suspension point (network I/O)
    ...
    await set_cached_ner(normalized_query, result)
```
`get_cached_ner`/`set_cached_ner` (and the `nosql_get`/`nosql_set` they call) have no internal `await` on real I/O — against the in-memory mock store, they run to completion without yielding control back to the event loop. The **first genuine suspension point** in this whole chain is the `httpx` call inside `llm_complete`. That means: if Task A (query X) and Task B (identical query X, e.g. two officers investigating the same active case — literally one of `test_chaos.py`'s own test phrases is `"same case"`) are both scheduled, Task A runs cache-check (miss) → enters the LLM call and yields at the real network I/O → Task B now runs → Task B's cache-check *also* misses, because A hasn't written back yet → Task B *also* calls the LLM. N concurrent identical queries produce N redundant LLM calls instead of 1.

Contrast this with `entity_lookup_resolver.py`, which correctly guards its own cache load with `asyncio.Lock()` + double-checked locking specifically to prevent this exact class of stampede (per its own comment: *"prevents a race condition where two concurrent invocations both find `_CACHE_LOADED=False` and both fire the DB load"*). The same protection pattern exists once in this codebase but was never applied to the NER cache, which is actually hit far more often (once per query, vs. once per cold container for the entity-lookup tables).
**Severity: High** — wasted LLM cost/latency under realistic concurrent load (multiple officers, or a burst of queries about the same case), with a proven-known fix pattern sitting unused one file away.

### 4. Read-during-write inconsistency between offline ingestion and the live query path
**Files:** `ingestion/pipeline.py::ingest_fir_to_graph`, `data/scripts/hydrate_cloud_graph.py::ingest_fir_to_graph`

FIR ingestion into Memgraph is multiple sequential `await run_write(...)` calls per record: create the FIR node, then separately `MERGE`+relate each accused, then separately each victim. There is no transaction wrapping these into one atomic unit. If a live query (`run_graph_step` in `executor.py`) runs concurrently with an ingestion batch — plausible if ingestion is ever re-run to add new records while the system stays up for a demo — a graph query could observe a FIR node that exists but has no accused/victim relationships yet (a genuinely partial, not-yet-complete record), silently returning incomplete evidence for that FIR with no indication it's mid-write rather than actually having no known associates.
**Severity: High** — narrow window in practice (ingestion is normally an offline batch step per `Agents.md`), but worth flagging since nothing in the code prevents running it while the system is live, and nothing would signal to a query that it hit a half-written record.

---

## 🟡 MEDIUM

### 5. Fire-and-forget task, reconsidered specifically under concurrent dispatch
**File:** `backend/job_dispatch.py:75` (`asyncio.create_task(_local_pipeline_runner(...))`, no reference retained)

Already flagged in the first audit pass as a GC-risk in isolation. Under concurrent load specifically: every query dispatched via the local-dev path spawns an independent, unretained background task. As concurrent query volume rises, so does the number of untracked in-flight tasks — there is no supervisor, no cap, and no way for the process to know how many pipeline runs are currently in-flight at once (relevant context for finding 1 and 2 above: nothing bounds how many overlapping same-session or duplicate-job runs could pile up).

### 6. SSE polling scales linearly with concurrent sessions, with no shared connection cap
**File:** `backend/sse_poller.py`

Each `/api/query` call opens its own `stream_job_status` generator, polling the shared in-memory job dict every 0.5s for up to 120s. This is not a leak (the loop always terminates), but there's no cap on the number of concurrent SSE connections a single AppSail process would hold open — under a burst of simultaneous officers querying, every one of them holds a live polling loop for up to 2 minutes. Combined with the already-established fact that this "NoSQL" layer is a single in-process dict (see `audit-report.md` C3), this is a scaling ceiling worth being aware of even though it isn't a bug per se at demo scale.

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical | 2 |
| 🟠 High | 2 |
| 🟡 Medium | 2 |
| **Total** | **6** |

**Why these matter more than they'd first appear:** every one of these is invisible in a single-user manual test (which is the only kind of testing this project's reports document — see `concurrency-audit.md`'s sibling, `test-validity-audit.md`, for why). They only manifest once real concurrent usage begins — which, for a system explicitly meant to serve multiple officers ("DYSP down to Constable" per `Agents.md`), is not a hypothetical scenario but the actual intended operating condition.

No code was modified during this pass.
