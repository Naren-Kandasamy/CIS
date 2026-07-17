# Security Audit Continuation — 2026-07-17

Continuation of the full-codebase security audit conducted earlier the same
session (Workflow-orchestrated, Sonnet-only, 62 confirmed findings across
API routes, RBAC, `get_lock` concurrency, exclusions/feedback/review-queue
engines — all reviewed and fixed in that earlier pass, uncommitted). This
document covers only the work done in this `/loop` continuation: the
ingestion-scripts audit, new test coverage for previously-unfixed routes, and
new findings discovered while writing that coverage.

All changes listed below are **uncommitted** on `feat/verifiable-intelligence`
pending explicit user go-ahead, per this session's standing rule.

## Ingestion scripts audit (`data/scripts/*.py`, `ingestion/pipeline.py`)

23 files in `data/scripts/` + `ingestion/pipeline.py`. Checked for injection
(f-string/`.format()`-built Cypher/SQL instead of parameterized queries),
unsafe deserialization, hardcoded secrets, command injection.

**Result: clean.** Every graph/SQL call uses parameterized queries
(`run_write(cypher, params)` / `ztsql_execute(sql, params)` with a separate
params list, never string-interpolated). No `eval`/`exec`/`pickle.load`/
`subprocess` with unsanitized input anywhere. The only credentials present
are the already-reviewed `dysp1`/`demo1234` demo-seed account (from
`seed_users.py`, intentionally documented as a rotate-before-real-use demo
credential), reused by two eval scripts to authenticate against the local
`/api/auth/login` for scripted evaluation runs — not a new leak.

Verified via a dedicated read-only subagent pass over all 18 files not
already read in this session (`ingest_all.py`, `hydrate_cloud_graph.py`,
`seed_users.py`, `test_token.py`, `ingestion/pipeline.py` were read directly).

## New findings (found + fixed this continuation)

| # | File | Issue | Fix |
|---|------|-------|-----|
| 1 | `backend/templates/report.html` | Autoescape fix from the earlier audit pass (enabling `select_autoescape` on the Jinja env to stop HTML injection via `query`/`answer`/`evidence`) caused a regression: the `\n → <br>` line-break conversion in `answer` now rendered as literal `&lt;br&gt;` text instead of real line breaks, since Jinja's `replace` filter doesn't preserve Markup-safety for a plain-string `new` argument under autoescape. | `{{ answer \| e \| replace('\n', ('<br>'\|safe)) }}` — explicitly escape first, then substitute a pre-marked-safe `<br>`. Verified end-to-end with a real `FileSystemLoader` render: injection payloads (`<script>`, `<img onerror>`) stay escaped, `\n` still produces a real `<br>`. |
| 2 | `client/src/App.tsx` | `handleLogout` only cleared `sessionStorage` client-side. The backend's `/api/auth/logout` (added in the earlier audit pass, calls `invalidate_session()`) was never called from the frontend — a token captured before "logout" (shared kiosk, browser history, proxy log) stayed fully valid for its remaining 8h TTL despite the officer believing they'd signed out. | `handleLogout` now fires a best-effort `POST /api/auth/logout` with the Bearer token before clearing local state (fire-and-forget so logout still works if the backend is briefly unreachable). |
| 3 | `backend/api/middleware/input_validator.py` | The generic JSON-body cap (`length > 2048` for any `application/json` POST) applied to **every** route, including `/api/export/pdf` — silently making `ExportRequest`'s own Pydantic limits (`answer` up to 20,000 chars, added in the earlier audit pass specifically to fit real report content) unreachable. Any real report with a substantive synthesized answer would 413 before the route, or Pydantic, ever ran. | Added a dedicated `/export/pdf` branch with a 256KB ceiling (generous enough for the route's own declared limits, still far below anything resource-exhausting) and restructured the size-check chain so path-match alone selects the branch — a request matching `/export/pdf` never falls through to the generic 2048-byte check regardless of whether it's under its own limit. |
| 4 | `backend/api/routes/query.py` | `QueryRequest.session_id` has no format restriction and shares NoSQL key prefixes (`session_owner:`, `history:`) with `cases.py`'s collaborator-ACL'd case sessions (id format `s_` + `token_hex(4)`, gated by `sessions.py`'s `_require_collaborator`). `/api/query`'s own ownership check is first-claim-wins with no case ACL — a session_id colliding with a real case session's id would piggyback onto that case's history, bypassing its collaborator check. Not exploitable today (the frontend never feeds a case-scoped id into `/api/query`, and the id space is only 32 bits — infeasible to guess under the 30/60s rate limit), but a real landmine for the pending case/session-integration cutover already noted in `cases.py`'s own scope comment. | Added a Pydantic `field_validator` rejecting any `session_id` starting with the reserved `s_` case-session prefix. Cheap, permanent separation of the two id namespaces regardless of future frontend wiring. |
| 5 | `functions/ps_1_cis_function/main.py` (primary production Signals-dispatched pipeline path), plus `pipeline_function/main.py` and its Function mirror `functions/ps_1_cis_function/pipeline_function/main.py` (both apparently vestigial today — nothing imports `pipeline_function.main` — but live, importable, tracked code) | All three had the same raw-exception info-leak (`error=str(e)`) already fixed earlier this session in `backend/job_dispatch.py`'s **local-dev-only fallback** runner, but missed in these three other copies of the same outer exception handler. `sse_poller.py` streams `job.error` straight to the browser over SSE — this is the more serious instance, since `functions/ps_1_cis_function/main.py` is the actual real production path (Signals dispatch), not the fallback. | All three now write a generic client-facing message (`"Pipeline processing failed, please retry."`), keeping the real exception in server-side logs (`traceback.print_exc()` / `logger.error()`) only. Verified `py_compile` clean on all four files; confirmed the two `pipeline_function/main.py` mirror copies stay byte-identical after the edit. |
| 6 | `pipeline_function/pipeline/query_understanding/dag_planner.py` (+ its Function mirror) | `build_dag()` spliced `json.dumps(intent_object)` directly into the DAG-planning LLM prompt with no delimiter wrapping — unlike `ner_prompt.py`/`synthesizer.py`/`confidence_engine.py`/`langgraph_router.py`, which all use an established random-token `<<<MARKER_...>>>` delimiter pattern specifically to stop prompt injection. `intent_object`'s entity fields are NER-extracted from the officer's raw query text and can carry attacker-influenced strings intact. Exploit blast radius was already bounded downstream (`retrieval/executor.py` never uses a DAG step's freeform `params` to build a raw query string — it reads `entities`/`evidence.query` directly and always parameterizes), but the gap broke the defense-in-depth pattern used consistently everywhere else in this pipeline. | Applied the identical random-token delimiter pattern from `shared/ner_prompt.py` (`<<<INTENT_{token}>>>` / `<<<END_INTENT_{token}>>>`, with a matching system-prompt instruction to treat the contents as literal data). Synced to the Function mirror, confirmed byte-identical, `py_compile` clean. |
| 7 | `pipeline_function/pipeline/langgraph_router.py`'s `synthesizing_response_node` (+ its Function mirror) — **this is the actual live synthesis path**, confirmed via `functions/ps_1_cis_function/main.py`'s import chain | Already wraps history/evidence in `HISTORY_START/END`/`EVIDENCE_START/END` blocks (an earlier fix), but the officer's `query` itself was spliced in with no delimiter at all — the same gap class as findings #6 and #8, in the code path that actually runs in production (unlike `synthesizer.py`'s `synthesize()`, which is only reachable via `graph_definition.py` — confirmed dead code per that function's own existing comment: "SYNTHESIS_SYSTEM (previously only reachable via dead code in graph_definition.py)"). | Applied the same `<<<QUERY_{token}>>>` delimiter pattern, with the inline system-prompt addendum updated to describe it alongside the existing history/evidence rules. Synced to the Function mirror, byte-identical, `py_compile` clean. No test asserts against the exact prompt string (checked `test_pipeline.py`), so this is a safe change. |
| 8 | `pipeline_function/pipeline/synthesis/synthesizer.py`'s `synthesize()` (+ its Function mirror) — dead code today (see finding #7), but live/importable/trackable | Already wraps evidence excerpts in `<evidence_excerpt>` tags (an earlier, higher-priority fix, since that vector is third-party OCR/KB content — attacker and victim can be different officers there). `evidence.query`/`ENTITIES` were still spliced in unwrapped, inconsistent with the pattern. Genuinely lower severity than finding #7's gap: since `evidence.query` here is the officer's own input, a self-directed prompt injection can't leak another officer's data — it can at most distort that officer's own synthesis output, which is already independently guarded by the in-code verification-disclaimer enforcement a few lines below. | Applied the same `<<<QUERY_{token}>>>` delimiter pattern to `evidence.query`, added a matching `SYNTHESIS_SYSTEM` rule. Synced to the Function mirror, byte-identical, `py_compile` clean. |

Findings #6-8 (the three delimiter fixes) were additionally verified with a
scratchpad script mocking each module's LLM call boundary and asserting, per
call: the delimiter markers are present in the actual outbound prompt text,
a crafted injection payload ("Ignore all previous instructions...") stays
contained inside them, and the surrounding logic (DAG JSON parsing, evidence
synthesis, LangGraph node state return) all complete correctly unaffected by
the prompt reformatting. All three passed.

## New test coverage added

No route-level tests previously existed for `auth.py`, `cases.py`, `query.py`,
or `export.py` — all their locking/validation/rate-limit logic (from the
earlier audit pass) had only been exercised via scratchpad live-test scripts,
never committed to the repo's test suite.

- **`test_auth.py`** — login success, wrong-password failure counter
  increment, lockout after max failures (429 before `authenticate()` is even
  called), logout revokes the token, unauthenticated logout rejected by RBAC.
- **`test_cases.py`** — unauthorized create, authorized create (writes to
  case doc + case_sessions + user index), the 403-unification anti-enumeration
  fix (nonexistent case_id and exists-but-not-a-collaborator both return the
  *identical* 403 body), successful collaborator add (both index writes),
  unknown-officer rejection.
- **`test_query.py`** — unauthorized, first-use session-id claim, cross-officer
  reuse blocked (403), same-owner reuse allowed, rate limit exceeded (429),
  oversized query text (400 — via `input_validator.py`'s dedicated `/query`
  check, not Pydantic), case-scoped session-id prefix rejected (finding #4
  above). Required an `autouse` fixture resetting `sse_starlette`'s cached
  `AppStatus.should_exit_event` between tests — its own documented workaround
  for a cross-event-loop error when chaining multiple SSE-returning tests
  through one `TestClient` process.
- **`test_export.py`** — unauthorized, insufficient rank (RBAC's
  `sub_inspector` minimum), oversized query/answer/evidence-count rejected,
  malformed evidence item → clean 400 (not an unhandled 500), WeasyPrint
  unavailable → 500, HTML-injection payloads verified escaped end-to-end
  through the real Jinja template while `\n → <br>` still renders correctly
  (finding #1 above), `_no_external_fetch` blocks `http://`/`file://` URLs.
- **`test_main_cors.py`** — `CORS_ALLOWED_ORIGINS=*` raises `EnvironmentError`
  at import time (the earlier audit pass's wildcard+credentials guard).
- **`test_sessions.py`** — unauthorized, session_id not found (404),
  non-collaborator denied (403, via `cases.py`'s shared `_require_collaborator`
  — confirms a session's access is correctly inherited entirely from its
  parent case's collaborator list), collaborator allowed (200, meta + history).
- **`test_exclusion_engine.py`** (new) — `create_exclusion`/`reverse_exclusion`'s
  duplicate-active-exclusion and double-reversal rejections (both real bugs
  fixed earlier this session, but only ever verified via a one-off scratchpad
  script against a disposable Memgraph container — never turned into
  permanent coverage until now), plus unknown-Accused/unknown-FIR rejection
  and `get_active_exclusions` keying.
- **`test_feedback.py`** (expanded) — added coverage for `_sanitize_scope_part`
  (the actual security fix preventing an `edge_type`/`crime_type` scope-key
  collision/poisoning attack), `record_feedback_event`'s broad+narrow
  increment writes, negative-verdict session-penalty application, and
  `get_session_penalized_ids`'s empty case — none of which the pre-existing
  tests (trust-math formula, API route wrapper) actually exercised.
- **`test_review_queue.py`** (expanded) — added coverage for
  `get_pending_review_items`/`get_review_item` skipping a malformed/
  schema-drifted row instead of 500ing (a real bug fix with no prior test),
  `fir_id`/`related_fir_id` filtering, and `push_review_item`'s
  write-then-verify retry loop actually retrying across multiple attempts
  when a concurrent writer clobbers the index.

- **`test_ocr.py`** / **`test_tts.py`** (new) — neither route had any prior
  coverage. `ocr.py` was reviewed fresh and found already well-hardened by
  the earlier audit pass (untrusted-document-content system prompt for the
  VLM call, output schema validation against `EXPECTED_FIR_FIELDS` rejecting
  a prompt-injected response, generic error messages, and no persistence —
  the extracted JSON is returned directly to the client, never fed back into
  the pipeline, so there's no second-stage injection risk from this route).
  Added 6 tests for OCR (unauthorized, success, unsupported MIME, upstream-
  failure info-leak check, schema-validation rejection, markdown-fenced JSON
  handling) and 5 for TTS (unauthorized, success, oversized/empty text
  rejection, upstream-failure info-leak check).

**Result: 77/77 passing** (`test_auth.py`, `test_cases.py`, `test_query.py`,
`test_export.py`, `test_main_cors.py`, `test_sessions.py`, `test_exclusion_engine.py`,
plus the expanded `test_exclusions.py`, `test_validator.py`, `test_review_queue.py`,
`test_zia_mocked.py`, `test_feedback.py` to confirm the `input_validator.py`
change caused no regressions elsewhere). Run in a fresh venv built only from
`backend/requirements.txt` (`venv_fresh_check`), not the long-lived dev venv.

`test_pipeline.py` was excluded from the regression run — it requires a live
Memgraph connection at collection time (pre-existing environment dependency,
unrelated to any change in this session). `test_ner.py`/`test_router.py` are
legacy manual scripts (`run_tests()` + `asyncio.run`, not pytest-native
`def test_*` functions) and correctly collect 0 pytest items — not a
regression.

## Dependency vulnerability audit

Ran `npm audit` (client) and `pip-audit` (backend, full installed dependency
tree) for authoritative, current vulnerability data rather than relying on
memory — all findings below carry 2026-dated advisory IDs, past this
assistant's training cutoff, so every one was independently researched via
WebSearch/WebFetch against primary sources (OSV.dev, GitHub Advisory
Database, CVE.org) rather than guessed at.

**Frontend (`npm audit`, both `--production` and full):** 0 vulnerabilities.

**Backend (`pip-audit`):** 22 known vulnerabilities across 8 packages
(`langchain-core`, `langgraph`, `langgraph-checkpoint`, `langgraph-sdk`,
`pytest`, `python-dotenv`, `starlette`, `weasyprint`). For every one, the
actual vulnerable API surface was checked against this specific codebase via
direct `grep` — not assumed from the package version alone. **None are
reachable in this application's current code:**

| Package | Vulnerability | Requires | This app's usage |
|---|---|---|---|
| `starlette` 0.37.2 (9 advisory entries — appear to be the same underlying CVE-2026-48710 tracked across multiple release branches) | Host-header `request.url` reconstruction bypass — middleware/routes checking `request.url.path` instead of the raw ASGI path can be bypassed | Code that reads `request.url`/`.url.path`/`request.base_url` for a security decision | Confirmed via grep: **zero** matches for `request.url`/`.url.path`/`request.base_url` anywhere in `backend/`. Both `RBACMiddleware` and `InputValidationMiddleware` — the only two places that make path-based security decisions — use `scope.get("path")` (the raw ASGI path) exclusively, verified by reading both files in full earlier this session. Not exploitable. |
| `weasyprint` 62.2 | PYSEC-2026-2034: SSRF protection bypass via HTTP redirect (a TOCTOU — a URL that passes custom validation, then redirects to a blocked target that never gets re-validated) | An app-supplied `url_fetcher` that *partially* validates/allows some URLs through | `export.py`'s `_no_external_fetch` unconditionally raises for **every** URL with no allowlist path — there is no "passes validation, then fetch follows a redirect" case for this bug to exploit, since nothing ever passes. Not exploitable. |
| `weasyprint` 62.2 | PYSEC-2026-3412 (CVE-2026-49452): CSS injection via unescaped HTML attributes when `presentational_hints` is enabled | `presentational_hints=True` passed to `HTML(...)` | `export.py`'s only `HTML(...)` call (`HTML(string=html_out, url_fetcher=_no_external_fetch).write_pdf()`) never sets `presentational_hints` (default `False`). Not exploitable. Also separately confirmed the *older*, already-patched CVE-2024-28184 ("PDF attachment bypasses url_fetcher") only affected WeasyPrint 61.0–61.1, fixed in 61.2 — well below the pinned 62.2. |
| `langgraph` / `langgraph-checkpoint` / `langgraph-sdk` | CVE-2026-28277 (unsafe msgpack deserialization of checkpoint data → RCE), CVE-2025-67644 (SQL injection in `SqliteSaver.list()`/`.alist()` via unparameterized f-string metadata filters) | A configured checkpointer (`.compile(checkpointer=...)`), and for the SQL injection specifically, `langgraph-checkpoint-sqlite`'s `SqliteSaver` | Confirmed via grep: `langgraph_router.py`'s only `.compile()` call is `workflow.compile()` — **no checkpointer argument at all**. No checkpoint data is ever persisted to or deserialized from any external store (SQLite, Postgres, or otherwise). Not exploitable. |
| `langchain-core` | CVE-2025-68664 (CVSS 9.3): serialization injection via the reserved `lc` key in `dumps()`/`dumpd()`, escalatable via prompt injection to RCE / secret extraction | Direct calls to `langchain_core.dumps()`/`dumpd()`/`load()`/`loads()` on LLM-generated structured output | Confirmed via grep: this codebase never imports from `langchain_core` at all and never calls `dumps`/`dumpd`. Every `json.dumps(...)` match found is Python's stdlib `json` module, unrelated. Not exploitable. |
| `langchain-core` | CVE-2026-34070: path traversal via `load_prompt()`/`load_prompt_from_config()` reading attacker-influenced file paths | Direct calls to `load_prompt()`/`load_prompt_from_config()` | Confirmed via grep: neither function is called anywhere in this codebase. Not exploitable. |
| `python-dotenv` 1.0.1 | PYSEC-2026-2270: `set_key()`/`unset_key()` follow symlinks on a cross-device-rename fallback, allowing arbitrary file overwrite | Calls to `set_key()`/`unset_key()` | Confirmed via grep: this codebase only ever calls `load_dotenv()` (read-only); `set_key`/`unset_key` are never called anywhere. Not exploitable. |
| `pytest` 8.3.3 | PYSEC-2026-1845 | N/A — test-only dependency, never present in the deployed Catalyst runtime (`backend/requirements.txt` marks it `# test-only`) | Not reachable in production regardless of the specific vulnerability. |

**Action taken:** bumped `jinja2` 3.1.4 → 3.1.6 in `backend/requirements.txt`
(the one dependency where a same-minor-version patch bump was zero-risk —
verified via a re-run of all 9 `test_export.py` tests plus a direct
`FileSystemLoader` render check against the upgraded version, both passing
identically). **Not** bumped: `fastapi`/`starlette`/`weasyprint`/`langgraph`.
`fastapi==0.111.0` hard-pins `starlette<0.38.0,>=0.37.2`, so patching
starlette requires a FastAPI major-version bump too; `weasyprint`'s fix
version (68.0) is six major versions ahead of the pinned 62.2. Both are
real, breaking-change-risk upgrades this environment can't fully
regression-test (no live Catalyst backend for FastAPI routing behavior;
WeasyPrint's native GTK/Pango libraries aren't even installed locally, per
this session's earlier note). Recommended as good hygiene / defense-in-depth
for the future — a later code change could introduce a `request.url`-based
check or a checkpointer without anyone recalling these specific CVEs — but
explicitly **not urgent** given every current usage was verified
unreachable, and **not performed** without the user's sign-off given the
regression-testing gap.

## Not yet done

- No dedicated test coverage added for `graph.py` (a stub, low priority) or
  `health.py` (trivial, low priority).
- The broader case/session-to-query integration (making `/api/query` require
  a case-registered session_id) remains explicitly out of scope, per
  `cases.py`'s own scope note — it's a breaking change to the frontend's
  current per-tab UUID contract and needs to land together with frontend
  rewiring, not ahead of it.
