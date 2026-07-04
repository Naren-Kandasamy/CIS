# PS-1 CIS — Test-Validity Audit

**Date:** 2026-07-04
**Auditor:** Claude (Sonnet 5), audit-only pass — no code modified
**Scope:** Not "does a test exist" but "does this test actually prove what it's presented as proving." For every test/eval/verify script in the repo, this pass checks: does it mock away the exact behavior it claims to validate, does it depend on undocumented execution order, does it assert loosely enough to pass on a broken system, and does it test the code path that's actually deployed. Every claim below is backed by a direct read of the current file plus, where relevant, a `grep` confirming coverage (or its absence) across the whole repo.

---

## 🔴 CRITICAL

### 1. The pipeline that's actually deployed has zero test coverage of any kind
**Files:** `pipeline_function/pipeline/template_router.py` (the pipeline `functions/ps_1_cis_function/main.py` — the deployed Catalyst Function — actually runs)

`grep -r "template_router|run_template_router"` across the entire repository returns exactly three non-documentation hits: the file's own definition, its one caller (`functions/ps_1_cis_function/main.py`), and this audit's own reports. **No test file — not `test_chaos.py`, not `test_router.py`, not `data/scripts/verify_trap_scenario.py`, not `test_ui_playwright.py` — ever imports or exercises `template_router.py`.** Every documented "passing" result in this repository (`Rigorous_Testing_Report.md`'s "13/13 chaos tests passed," the trap-scenario "launch blocker cleared," the manual Playwright E2E walkthrough) runs exclusively through `langgraph_router.py`, via `_local_pipeline_runner` (local dev) or `pipeline_function/main.py` (also not the deployed function per `catalyst.json`).

This is the single most consequential test-coverage gap in the project: **the code path that ships to production has never been executed by any automated or documented manual test.** Combined with the cascading-logic audit's finding that `template_router.py` skips the Confidence Engine entirely, there is currently no test in this repository that would have caught that gap, because no test ever runs that file.
**Severity: Critical.**

### 2. The "13/13 chaos tests passed" result doesn't test what it's presented as testing
**File:** `test_chaos.py` (imports `run_langgraph_pipeline` from `langgraph_router.py`)

Independent of coverage: per `cascading-logic-audit.md` finding 1, `langgraph_router.py`'s graph retrieval never actually filters by any extracted entity (a wrong dict key silently zeroes out `city`/`locations`/`crime_types`/`weapon` before they reach the Cypher query), so every graph-routed query returns the same generic unfiltered top-10 FIR dump regardless of input. `test_chaos.py`'s 13 adversarial queries — including deliberately nonsensical ones like `"Find me a murder case involving a lightsaber in Antarctica"` — are specifically designed to check that *adversarial input doesn't break retrieval*. But if graph retrieval structurally ignores its input entirely, it cannot meaningfully distinguish "Antarctica lightsaber murder" from "robbery in Belagavi" — both would hit the identical bare `MATCH (f:FIR) WHERE 1=1 LIMIT 10` query. The reported 13/13 pass rate reflects "the pipeline didn't crash," which the test's own assertions (`if not captured_result.get("answer"): FAILED`) do check — but it provides essentially no evidence that entity-based retrieval correctly discriminates between these very different queries, because that mechanism was never actually engaged.
**Severity: Critical** — this doesn't just miss a bug, it actively produces a misleadingly reassuring "all adversarial cases handled" narrative for a mechanism that structurally can't fail differently based on adversarial input in the first place.

---

## 🟠 HIGH

### 3. The NER quality gate (`eval_ner.py`) was run against a different model than the one that ships
**File:** `data/scripts/eval_ner.py:97`, `shared/catalyst_client.py:55-72`, `Docs/PS1_Architecture_v8.md:48`

```python
# Run sequentially to avoid aggressive rate limits on Groq
```
This comment in the eval harness confirms the NER pass-rate gate (`if pass_rate >= 90.0: sys.exit(0)`) was routinely run against Groq's `llama-3.3-70b-versatile`, reached via the `GROQ_API_KEY` branch in `llm_complete` (`shared/catalyst_client.py`) — not the Qwen 14B model documented as the actual production LLM. `PS1_Architecture_v8.md` line 48 confirms this Groq path is intentional and documented ("LLM fallback | Groq + Llama 3.1 70B (offline/dev only) | **Not for production**") — so this isn't a rogue backdoor, it's a deliberate dev-cost-saving shortcut. But that makes the gap sharper, not smaller: **the documented "not for production" boundary is enforced nowhere in code** — no environment check, no startup warning, no test that verifies Groq is actually disabled in whatever counts as "production" for this deployment — and the NER accuracy number this eval produces was measured against a materially different model (different training data, different prompt-following behavior) than what real officers' queries are parsed by. A 90%+ pass rate against Llama 3.3 70B is not evidence of a 90%+ pass rate against Qwen 14B.
**Severity: High.**

### 4. `test_ner.py`'s "cache hit" test only passes because of an undocumented dependency on test execution order
**File:** `test_ner.py`, tests #1 and #2 inside `run_tests()`

```python
# 2. Test cache hit
# The previous test should have cached it!
with patch(...) as mock_llm:
    res = await extract_ner_and_intent("Find Ravi")
    mock_llm.assert_not_called()  # Should use cache
```
The comment *"The previous test should have cached it!"* is a self-acknowledged order dependency: test #2 only passes because test #1 ran first, in the same process, against the same shared in-memory `_mock_nosql_cache`, and populated the cache as a side effect. This isn't just the previously-documented "not pytest-compatible" tooling gap (`CIS_audit_report.md`) — it's a deeper issue that simply adding `@pytest.mark.asyncio` decorators (the fix that report recommends) would not solve on its own. Real pytest test functions run as independently as the test runner allows and are frequently reordered, parallelized, or run individually during debugging; test #2 as currently written would need to be restructured to explicitly seed its own cache precondition, or it will silently break the moment this suite is migrated to isolated test functions.
**Severity: High** — a specific, actionable gap in a recommendation (pytest migration) that's already been made twice in prior audits but never actually attempted.

### 5. `test_validator.py`'s "safe queries allowed" check proves the endpoint returned 200, not that the query was correctly processed
**File:** `test_validator.py`, safe-queries loop

```python
for q in safe_queries:
    r = client.post("/api/query", json={"session_id": valid_session, "query": q})
    assert r.status_code == 200, f"Expected 200 for safe query '{q}', got {r.status_code}..."
```
`/api/query` returns a `200` with a streaming SSE body immediately upon accepting the request — before `dispatch_query_job` even resolves whether the query will succeed. This assertion only proves the input-validation middleware let the request through; it never reads the SSE stream body, never checks for an `event: error` frame, and never confirms a real answer was produced. Worse: because no `CATALYST_SIGNALS_PUBLISHER_URL` is configured in a typical dev run, each of the 5 "safe" queries in this loop triggers `asyncio.create_task(_local_pipeline_runner(...))` — a real, unawaited, fire-and-forget background pipeline execution (potentially real LLM calls) that the test function does not wait for, does not verify, and has likely not finished by the time the test script prints "✅ All input validation tests passed successfully!"
**Severity: High** — a "200 is reachable" result is being reported as "queries work," the exact conflation this project's own downstream documentation should be most careful to avoid for a system whose outputs inform police action.

---

## 🟡 MEDIUM

### 6. `pytest` still collects 0 tests — a gap flagged in the very first audit (2026-07-01), still unaddressed
**Repo-wide** — confirmed via direct check: no `pytest.ini`, `pyproject.toml`, `conftest.py`, or `setup.cfg` exists anywhere in the repository as of this pass. `CIS_audit_report.md` flagged this on 2026-07-01; three audit rounds and multiple commits later, it's still true. This means there is still no CI-runnable, coverage-reportable test suite — every test file in this repo is a standalone script that a human must remember to run and read the console output of.

### 7. `verify_stories.py`/`verify_trap_scenario.py` depend on an unenforced manual run-order
**Files:** `data/scripts/verify_stories.py`, `data/scripts/run_mage_algorithms.py`

`verify_stories.py` checks for `page_rank_score`/`centrality_score` on planted accused nodes and, on failure, prints *"Did you run run_mage_algorithms.py?"* — i.e., the script itself documents that its own precondition depends on a human remembering to run a separate script first, with nothing automated enforcing or checking that order. This is a soft version of finding 6: real correctness signal exists, but only if operated in a specific undocumented sequence.

### 8. `test_router.py` has no assertions at all — it cannot fail
**File:** `test_router.py`

The script prints the generated DAG and the pipeline's final answer/evidence count, but contains no `assert`, no exit-code check, nothing that would make the script exit non-zero if the output were wrong. It's a manual-inspection script, not a test, despite living alongside files that *do* assert (`test_ner.py`, `test_validator.py`, `test_chaos.py`) — easy to mistake for automated coverage of the full pipeline sequence when reading the file list, but it provides none.

---

## Summary

| Severity | Count |
|---|---|
| 🔴 Critical | 2 |
| 🟠 High | 3 |
| 🟡 Medium | 3 |
| **Total** | **8** |

**The throughline:** this project has a genuine testing culture (chaos tests, resilience tests, a trap-scenario safety check, an NER eval gate with a numeric threshold) — the scripts aren't lazy or absent. But nearly every one of them was validated against the wrong target: the untested-in-production pipeline copy, a different LLM than what ships, or an assertion loose enough to pass regardless of whether the real work happened. The "all green" status this project has reported at each checkpoint is real *for what was actually being measured* — it just measured a narrower and different thing than the checkpoint claims.

No code was modified during this pass.
