# PS-1 CIS — Cascading & Cross-Module Logic Audit

**Date:** 2026-07-04
**Auditor:** Claude (Sonnet 5), audit-only pass — no code modified
**Scope:** Not a per-file bug/leak/credential sweep (see `Docs/audit-report.md` for that). This pass traces **contracts between functions and modules** — what a producer writes vs. what every consumer assumes it wrote — looking specifically for places where two code blocks silently disagree, one overwrites or discards another's work, or a value that "looks wired" in one file never actually arrives from its supposed source. Every finding below was verified by reading the current, exact producer and consumer code side by side (not inferred from names or docstrings), with several confirmed via fresh re-reads and targeted `grep` in this session.

---

## 🔴 CRITICAL

### 1. The tested pipeline's graph retrieval never actually filters by anything — a wrong dict key silently discards every extracted entity
**Files:** `pipeline_function/pipeline/langgraph_router.py:70` (producer) vs. `pipeline_function/pipeline/retrieval/executor.py:24-26` (`run_graph_step`, consumer)

`retrieving_evidence_node` in `langgraph_router.py` calls:
```python
evidence_obj = await execute_retrieval(state["dag"], evidence_obj, {"intent_object": intent_obj})
```
passing a dict keyed `"intent_object"`. That dict flows unchanged into `run_graph_step(step, state)`, which reads:
```python
intent = state.get("intent", {})
entities = intent.get("entities", {})
city = entities.get("city", "")
locations = entities.get("locations", [])
crime_types = entities.get("crime_types", [])
weapon = entities.get("weapon", "")
```
`state.get("intent", ...)` looks for key `"intent"` — the dict only has `"intent_object"`. `.get()` doesn't raise; it silently returns `{}`, so `entities` is always `{}`, and `city`/`locations`/`crime_types`/`weapon` are always empty. None of the `if city:` / `if locations:` / `if crime_types:` / `if weapon:` blocks ever add a Cypher `WHERE` clause. Every graph-routed query — regardless of what the officer actually asked — executes the bare fallback:
```cypher
MATCH (f:FIR) WHERE 1=1 RETURN ... LIMIT 10
```
returning an arbitrary top-10 dump of FIRs (Memgraph's natural scan order), completely disconnected from the query.

**Compare `template_router.py:53`** (the file the *deployed* Catalyst Function actually runs):
```python
evidence_obj = await execute_retrieval(dag_plan, evidence_obj, state={"intent": intent_obj})
```
This one uses the correct key `"intent"` — so entity-filtered graph search actually *works* through `template_router.py`.

**Why this is critical, and why it's a "cascading" bug rather than a simple typo:** `langgraph_router.py` is the pipeline exercised by every piece of local verification in this repo — `test_chaos.py`, `test_router.py`, `data/scripts/verify_trap_scenario.py` (the "launch blocker" check), and the manual E2E walkthrough in `Rigorous_Testing_Report.md` ("Show me robbery cases in Belagavi in Belagavi" reportedly returning sensible results). None of that testing would have caught this, because:
- `run_rag_step(step, evidence.query)` passes the raw query string directly (not through `state`), so **KB/semantic-search results are unaffected** and can mask the graph-side failure whenever the DAG plan also includes a `rag` step, or whenever the officer's phrasing happens to hit the KB.
- A location- or crime-type-specific query that gets routed to `"graph"` type would silently return generic, unfiltered FIRs that "look plausible" in a small demo dataset without anyone noticing the filter never fired.

The two pipeline copies disagree on the exact contract shape passed into a shared function, and the one that's actually deployed happens to be correct here — the inverse of most of the divergences found in the first audit pass, and a strong reason not to trust "it looked right in my manual test" as proof this code path works in general.

### 2. The only synthesis prompt with citation rules, confidence-tier language, and the mandatory officer-verification disclaimer is unreachable dead code
**Files:** `pipeline_function/pipeline/synthesis/synthesizer.py` (`SYNTHESIS_SYSTEM`, only caller) vs. `langgraph_router.py:199` and `template_router.py:173` (both live pipelines' own inline prompts)

`synthesizer.py::synthesize()` uses a carefully written system prompt:
```
- Cite every factual claim with its source (FIR ID / graph path / algorithm)
- Use "appears as accused in FIR" -- NEVER "committed"
- Flag low-confidence results explicitly -- never present as certain
- HIGH confidence: state as fact. MEDIUM: use qualifier. LOW/UNVERIFIED: flag for verification
- Never fabricate connections not in evidence
- Always end with: "All outputs require officer verification before action."
```
`grep` for `synthesize(` across the entire repo shows exactly one caller: `pipeline_function/pipeline/graph_definition.py:75`. `graph_definition.py::run_pipeline_stages` was already confirmed (in the prior audit pass) to have **zero live callers anywhere** — not `pipeline_function/main.py`, not `functions/ps_1_cis_function/main.py`, not even `test_router.py` (which now imports `run_langgraph_pipeline` instead). So this prompt is only ever invoked by code nothing calls.

Both files that actually run in practice use their own, much thinner inline prompt instead — verified identical in both:
```python
system = "You are an AI assistant for the PS-1 police system. Answer based ONLY on the evidence provided."
```
No citation requirement. No confidence-tier language calibration. No fabrication guardrail beyond "based only on the evidence." And — the most consequential omission — **no instance of "All outputs require officer verification before action" anywhere in either live prompt.** `Agents.md` (§6) frames that exact disclaimer as one of two architectural rules that exist "specifically to prevent confident-sounding wrongness" for "a crime-intelligence tool whose outputs get read by field officers." Neither the pipeline that's tested locally nor the one that's deployed ever produces it.

**This is the connective finding that ties several others together**: the confidence engine (finding 3 below), the evidence metadata carrying `confidence_reasons`/`confidence_flags` (finding 4), and this prompt were all clearly designed as one coherent trust/explainability system — but the wiring that would deliver any of it to an officer only exists in a branch of the codebase nothing invokes.

### 3. Confidence scoring is either skipped, or silently discarded before display — differently, in each live pipeline
**Files:** `pipeline_function/pipeline/evidence.py:39-54` (`add_graph_results`), `pipeline_function/pipeline/confidence_engine.py:74-85` (`run_confidence_engine`), `template_router.py:56-63`, `langgraph_router.py:189-197`

`add_graph_results` hardcodes a hand-set confidence when a graph hit converges with an existing RAG hit:
```python
existing.confidence = "high"
existing.relevance_score = min(existing.relevance_score * 1.3, 1.0)
```
`run_confidence_engine` (a completely independent scoring pass — source convergence 45% + evidence strength 40% + recency 15%) then **unconditionally overwrites both fields for every item**:
```python
item.confidence = sig.tier
item.relevance_score = sig.score
```
- `langgraph_router.py`'s `confidence_scoring_node` calls `run_confidence_engine` — so the hardcoded `"high"`/`1.3x` from `add_graph_results` is always immediately discarded and replaced by the real computed score. The `1.3x` convergence boost is dead arithmetic; convergence is separately (and correctly) re-captured by `compute_source_convergence()` checking `item.sources`, so the *intended effect* (converged evidence scores higher) still happens, just via a completely different, redundant code path — the boost in `evidence.py` does nothing.
- `template_router.py` **never calls `run_confidence_engine` at all** (established in the prior audit pass). So there, the hardcoded `confidence="high"` from `add_graph_results` *would* survive on `EvidenceItem`... except `template_router.py`'s own evidence-dict serialization for both the synthesis prompt and the frontend response only includes `source`, `fir_id`, `data`:
```python
evidence.append({"source": ",".join(item.sources), "fir_id": item.fir_id, "data": item.metadata})
```
`confidence` is never included. So in the deployed function, confidence information is lost **twice over** — never computed by the real engine, and then the one hardcoded fallback value that does exist is dropped during serialization anyway. No confidence signal of any kind — not even the crude hardcoded one — reaches the officer-facing evidence panel or the LLM synthesis prompt in production.
- `langgraph_router.py`, by contrast, both computes confidence correctly and includes it in the evidence dict sent to the frontend (`"confidence": item.confidence, "relevance_score": item.relevance_score` — confirmed present in both the synthesis-prompt evidence_dicts and the final `result_data` sent to the SSE `evidence` event).

### 4. `confidence_flags` — the specific caveat text — is computed and stored, but never read by anything
**Files:** `confidence_engine.py:80` (sets `item.confidence_flags = sig.flags`), `evidence.py:14` (field declaration)

`grep` for `confidence_flags` across the whole codebase turns up exactly two hits outside documentation: the assignment in `confidence_engine.py` and the dataclass field declaration in `evidence.py`. Nothing — not `synthesizer.py`'s `items_text` formatting, not the `reasoning_trace` construction (which uses `sig.reasons`, a *different* list, not `sig.flags`), not either live pipeline's evidence-dict output — ever reads it back. Specific, high-value caveats computed by `compute_evidence_strength()` — `"Physical descriptor -- not forensically confirmed"`, `"Temporal proximity alone does not establish connection"`, `"No direct graph relationship -- similarity only"` — are generated purely to be discarded. Combined with finding 2, the system's explainability design (compute a specific reason something is weak evidence → surface it so a human doesn't over-trust it) is fully built on the writing side and never connected to any reading side.

### 5. Evidence metadata field names disagree across sources that all feed the same visualization — KB/RAG-sourced evidence silently shows as "Unknown" with no date
**Files:** `ingestion/pipeline.py:26-32` (KB metadata writer) vs. `langgraph_router.py:101,141,169` / `template_router.py` (visualization reader, identical logic in both)

`ingestion/pipeline.py::ingest_fir_to_kb` uploads this metadata to the Catalyst KB:
```python
metadata = {
    "fir_id": ..., "crime_no": ..., "district": fir.get("district_name", ""),
    "crime_sub_head": fir.get("crime_sub_head_name", ""), "ocr_extracted": ...
}
```
Note the keys: `crime_sub_head`, **no** `crime_type`, **no** `date`/`Date` at all.

`add_rag_results` (evidence.py) copies this dict through verbatim as `item.metadata`. Both `building_visualization_node` (langgraph_router.py) and its near-duplicate in `template_router.py` then build the dashboard charts by reading:
```python
ctype = item.metadata.get('crime_type', 'Unknown')       # donut chart — crime-type distribution
date_str = item.metadata.get('Date', '')                 # trend chart — monthly aggregation
```
Neither `crime_type` nor `Date` exists on KB/RAG-sourced metadata — only `crime_sub_head` and `district` do. So **every piece of evidence that came from the Knowledge Base / semantic search is silently bucketed as `"Unknown"` in the Crime Distribution donut chart and contributes to nothing in the Crime Trends line chart**, with no error, no log line, nothing — it just quietly under-counts. (`district` happens to match by coincidence and works correctly for the map markers.)

By contrast, `run_graph_step`'s Cypher `RETURN` clause maps Memgraph properties to keys `crime_type` and `Date` (capital D) explicitly, so graph-sourced evidence *is* correctly bucketed — meaning the correctness of these charts depends entirely on which retrieval source happened to surface a given FIR, a fact invisible to anyone looking at the rendered dashboard.

**Compounding factor:** given finding 1 (graph retrieval in the tested pipeline never actually filters, so it returns generic FIRs rather than query-relevant ones) and the previously-established SQL-path breakage, KB/RAG search is often the *only* retrieval path returning genuinely query-relevant evidence in practice — which is exactly the metadata shape that gets mis-bucketed here. The chart is most wrong precisely when it matters most.

---

## 🟠 HIGH

### 6. `city` and `weapon` entity fields are read by retrieval but never produced by NER, independent of the key-mismatch bug above
**Files:** `shared/ner_prompt.py` (`NER_INTENT_SYSTEM`) vs. `pipeline_function/pipeline/retrieval/executor.py:28,33` (`run_graph_step`)

Even setting finding 1 aside, `run_graph_step` reads `entities.get("city", "")` and `entities.get("weapon", "")`. The NER system prompt's `Expected JSON format` only ever instructs the LLM to populate `persons, locations, fir_ids, dates, ipc_sections, crime_types` — there is no `city` or `weapon` key anywhere in the schema, the rules, or any of the ten few-shot examples in `shared/ner_examples.py`. `Docs/Queries_example` (the project's own sample test queries) includes weapon-centric prompts explicitly designed to exercise this ("...involving an iron rod or blunt object", "...threatened the victim with a knife") — but the field that would carry that extraction into the graph filter is architecturally never populated upstream. This is a second, independent reason the weapon-filter branch of `run_graph_step` can never fire, layered underneath the key-name bug in finding 1 — fixing finding 1 alone would not make weapon-based graph filtering work.

### 7. DAG-planner fallback plan silently triples the same graph query instead of doing "assembly" and "synthesis"
**Files:** `pipeline_function/pipeline/query_understanding/dag_planner.py:33-38` (`_default_plan`) vs. `executor.py:128-145` (`execute_retrieval`)

When the DAG-planning LLM call fails or returns unparseable JSON, `_default_plan()` returns three steps typed `"graph"`, `"evidence_assembly"`, and `"synthesis"`. But `execute_retrieval`'s dispatch only recognizes `"graph"`, `"rag"`, `"sql"` (plus a `"data_retrieval"/"retrieval"` alias for `"graph"`); anything else falls into:
```python
else:
    coro = run_graph_step(step, state)  # Default fallback
```
So `"evidence_assembly"` and `"synthesis"` — clearly meant as non-retrieval bookkeeping steps — both get executed as full `run_graph_step` graph queries. Every DAG-planner failure fires the same Cypher query three times instead of once (deduped on merge by `add_graph_results`' existing-item check, so the *result* isn't tripled, but three Memgraph round-trips happen where the plan's own labels imply only one retrieval and two non-retrieval steps).

### 8. Two different silent default values for the same missing-key scenario, one of which the rest of the system never anticipates
**Files:** `langgraph_router.py:60` vs. `template_router.py:48`

```python
# langgraph_router.py
urgency = intent_obj.get("urgency", "analytical")
# template_router.py
urgency=intent_obj.get("urgency", "low")
```
The NER schema only ever specifies `"urgency": "analytical" | "field_urgent"` — `"low"` is not a value either the NER prompt or `synthesizer.py`'s `if evidence.urgency == 'field_urgent'` branching logic was written to expect. Since raw LLM JSON output is never schema-validated anywhere in `extract_ner_and_intent` (a `json.loads()` with no Pydantic check), a response missing the `urgency` key is plausible, and the two pipelines would silently diverge in behavior for the exact same malformed input — one falls back to the documented value, the other to an undocumented one that just happens to fall through every downstream `== 'field_urgent'` check into the "analytical-style" branch by accident rather than by design.

### 9. `run_langgraph_pipeline` has no internal exception handling — the "graceful failure" safety net is duplicated ad hoc per caller, and two callers don't have it
**File:** `langgraph_router.py:215-266` (`run_langgraph_pipeline`, no `try`/`except` anywhere in the function body)

Both real deployment entrypoints (`pipeline_function/main.py::_run_pipeline`, and separately `functions/ps_1_cis_function/main.py`, though that one calls `run_template_router` instead) wrap their call to the pipeline in `try/except Exception: write_job_status(..., status="failed", ...)`. But `run_langgraph_pipeline` itself has no such guard, so any caller that forgets to add one gets an unhandled exception instead of a graceful failure. Two callers do forget: `test_router.py::main()` and `data/scripts/verify_trap_scenario.py::verify_trap_scenario()` — the latter being the project's designated "launch blocker" safety check. A transient failure inside any node (an uncaught exception type from a malformed LLM response, for instance) would crash that verification script with a raw traceback instead of reporting a clean pass/fail, which is a confusing failure mode for a check specifically meant to be run with confidence right before a demo.

---

## 🟡 MEDIUM

### 10. The DAG planner's own prompt references an intent value the NER layer can never produce
**Files:** `dag_planner.py` (`DAG_PLANNER_SYSTEM`) vs. `shared/ner_prompt.py`

`DAG_PLANNER_SYSTEM` instructs: *"Use 'rag' when the intent is `similarity_search`..."* — but `NER_INTENT_SYSTEM`'s intent enum is `lookup, summarize, graph_search, statistics, compare`. `similarity_search` is never a value the NER stage can emit. Because both prompts drive an LLM rather than deterministic branching, this doesn't hard-fail (the planner's alternate clause, "...or when searching for a specific modus operandi narrative," gives it another route to select `"rag"`), but it's a real drift between two independently-authored prompts that reference each other's output schema without a shared constant, and a future edit to one is unlikely to be checked against the other.

### 11. The SSE "token" event delivers the entire answer at once — the name implies incremental streaming that never happens
**File:** `backend/sse_poller.py:29` vs. `client/src/App.tsx:115-117`

```python
yield {"event": "token", "data": json.dumps({"token": result.get("answer", "")})}
```
sent exactly once, containing the full final answer text — not per-token. The frontend handler is written generically enough to just display whatever arrives (`content: data.token`), so nothing breaks, but the naming across both ends of this contract implies a streaming design that was never implemented; if anyone later adds real token-by-token delivery, they'd need to change the event semantics (multiple `token` events) without breaking the current single-shot consumer, and nothing currently documents that this event is single-shot.

### 12. The Dashboard tab's "Analytics Dashboard" is really just a mirror of the single most recent chat answer
**Files:** `client/src/App.tsx:245` (`<DashboardPanel visualization={messages.filter(m => m.role === 'assistant').pop()?.visualization} />`)

The Dashboard view has no independent data source — it always reflects whichever assistant message was most recently appended to the chat. Ask a follow-up question that returns zero `fir_ids` (very possible given findings 1 and 6 above), and the Dashboard's charts all silently reset to empty (`visualization` stays at its all-empty default from `building_visualization_node` when `fir_ids` is falsy), even if an earlier query in the same session had rich data. The tab is framed as a persistent analytics overview but behaves as a single-query side effect.

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical | 5 |
| 🟠 High | 4 |
| 🟡 Medium | 3 |
| **Total** | **12** |

**The throughline across this pass:** this codebase has several places where two halves of the same intended feature were clearly written by the same design (confidence scoring → confidence-aware synthesis; NER entity extraction → entity-filtered retrieval; ingestion metadata → dashboard visualization) but the connective wiring between the two halves is either using mismatched key names, pointing at dead code, or getting silently overwritten/dropped one step downstream. None of these are crashes — every single one degrades silently into a plausible-looking but disconnected-from-reality result (generic FIRs instead of filtered ones, "Unknown" instead of a real crime type, no confidence label instead of a computed one, a generic disclaimer-free answer instead of the carefully designed one) — which is exactly why none of them were caught by manual testing or prior line-by-line audits: every individual file, read in isolation, looks reasonable.

No code was modified during this pass. Awaiting direction on which findings to triage first.
