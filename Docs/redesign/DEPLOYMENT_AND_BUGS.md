# Deployment issues & bug log — CIS

A reference of every deployment failure and bug hit while shipping the
redesigned workspace to Zoho Catalyst, with **root cause** and **fix** for
each, so a future session can resolve the same class of problem fast.

Last updated: 2026-08-30, after `main` commit `e1f4ebb`. Demo video was
recorded; the `< P0 >` items below were fixed, `< known >` items are
deferred to "if we get selected for the next round".

Companion docs: `FULL_CHANGELOG.md` (what shipped), `SESSION_HANDOFF.md`,
`PHASE_HANDOFF.md`, `INDIC_ASR_INTEGRATION.md`.

---

## Quick reference — deployed URLs & accounts

| Thing | Value |
|---|---|
| Web app | `https://ps1-cis-60075634347.development.catalystserverless.in/app/` |
| Backend AppSail | `https://backend-50043491738.development.catalystappsail.in` |
| Catalyst console | `https://console.catalyst.zoho.in/` → project **PS1‑CIS** (PID `45958000000015001`, org `60075634347`, DC **India / .in**) |
| Demo logins | `dysp1` / `inspector1` / `si1` / `constable1` — **all** password `demo1234` |
| Client `VITE_API_BASE_URL` | set in `client/.env.production` → the AppSail URL above |

Deploy: `catalyst deploy` (all) or `catalyst deploy --only client|appsail|functions`.
CLI 1.27.0, logged in via `catalyst whoami`.

---

# A. Deployment issues (Catalyst)

## A1. `< P0, FIXED >` Everything on the project domain returns `INVALID_URL`

**Symptom.** `https://ps1-cis-…catalystserverless.in/app/index.html` (and every
other path on that domain) returns
`{"status":"failure","data":{"error_code":"INVALID_URL", …}}`. `/` 302-redirects
to `/app/`, which then fails the same way. `catalyst deploy --only client`
reports **SUCCESS** anyway. The **AppSail backend on its own domain works fine**
(login, API all OK).

**Root cause.** **API Gateway was enabled on the project with zero routes
configured.** Once API Gateway is on, it intercepts *all* traffic to the project
domain (`…catalystserverless.in`) — web client included — and returns
`INVALID_URL` for anything without an explicit gateway rule. The console page
says it outright: *"Default system generated functions and web client URLs will
not be accessible directly unless you configure them in API Gateway."* The
AppSail backend was unaffected because it has a **separate dedicated domain**
(`backend-…catalystappsail.in`) that bypasses the project-domain gateway.

**Fix.** Console → **Cloud Scale → API Gateway → "…" menu → Disable.** Takes
effect in ~1 min; `/app/` then serves 200. Reversible.
This project does **not** need API Gateway: the client talks to the backend via
the dedicated AppSail URL, and the pipeline runs via Signals (event bus, not an
HTTP API). Nothing routes through the project-domain gateway.
*(Alternative, more work: add a gateway rule `/app/**` → Web Client, plus rules
for every function endpoint.)*

**How to check next time.**
```
curl -s -o /dev/null -w "%{http_code}\n" https://ps1-cis-60075634347.development.catalystserverless.in/app/
```
200 = fine. 404 + `INVALID_URL` JSON = API Gateway is on with no rules → disable it.

## A2. `< done >` Deep links 404 on the static host — switched to HashRouter

**Symptom.** Even once `/app/` served, a hard refresh on a deep route
(`/app/cases/xyz`) would 404 — Catalyst static hosting has no SPA-fallback
rewrite to `index.html`.

**Fix.** `client/src/router.tsx`: `createBrowserRouter({basename:'/app'})` →
**`createHashRouter`** (no basename). Routes now live after `#`
(`/app/index.html#/cases`), so the server only ever sees `/app/index.html`.
Commit `18367d3` (by Naren). No other code changes needed — checked: no
`window.location` / hard-coded `/app` links; `RequireAuth` uses
`useLocation().pathname` which is the hash path under HashRouter.

## A3. `< P0, FIXED >` Evidence not persisting on the *deployed* stack

**Symptom.** Locally, a reloaded session restored evidence cards + graph + map
(the `{q,a,evidence,visualization}` history fix). On the deployed app, reloaded
sessions still showed answer text only. A deployed-backend e2e query returned
`evidence=0` / no `visualization` key in the history turn.

**Root cause.** **The evidence-persistence change was mirrored into the wrong
file.** The Signals function's actual entrypoint is
`functions/ps_1_cis_function/main.py` (per `catalyst-config.json`
`execution.main`). The earlier fix went into
`functions/ps_1_cis_function/pipeline_function/main.py`, which is *not* the
entry — it's a stale sibling. The real entrypoint still did
`history.append({"q": query, "a": result_data.get("answer", "")})`.

**Fix.** Commit `e1f4ebb`: added `evidence` (capped `[:40]`) + `visualization`
to the history append in `functions/ps_1_cis_function/main.py`, then
`catalyst deploy --only functions`. Verified: fresh query →
`keys=['q','a','evidence','visualization'] evidence=2 viz=True`.

**Lesson.** The Signals entrypoint is `functions/ps_1_cis_function/main.py`, NOT
`functions/ps_1_cis_function/pipeline_function/main.py`. When touching the
pipeline's history/result handling, grep for **all** `history.append` across
`backend/job_dispatch.py`, `pipeline_function/main.py`,
`functions/ps_1_cis_function/main.py`, and
`functions/ps_1_cis_function/pipeline_function/main.py` and reconcile every one.

## A4. `< known, DEFERRED >` Pipeline crashes on warm containers

**Symptom.** First query on a fresh/cold function container works (~5 s, full
answer + evidence + viz, persists fine). **Subsequent queries on the same warm
container hang** — the frontend never gets a result, no history is written.

**Root cause (from function logs, DevOps → Logs → Application → `ps_1_cis_function`).**
```
[Pipeline Error] run_langgraph_pipeline failed: cannot schedule new futures after shutdown
connect_tcp.failed exception=RuntimeError('cannot schedule new futures after shutdown')
```
The **anyio / httpx global `ThreadPoolExecutor` is left in a shut-down state
between warm invocations.** `functions/ps_1_cis_function/main.py` already carries
several workarounds for this (persistent global `_loop`, clearing
`langchain_core.callbacks.manager._executor` cache each `handler()` call) — they
reduce but do not eliminate it.

**Status.** Pre-existing; long trail of prior fix attempts on `main`
(`fb5a237`, `d01e8ed`, `32da3a6`, `e9df7c0`, `12ffe37`, `9cbedc1`). **Not fixed
this session** — deep, previously-costly, and a bad patch right before a demo is
worse than a known limitation.

**Demo workaround.** `catalyst deploy --only functions` immediately before
recording (forces cold containers); do the first query per session and space
them out. If one hangs, the container went warm — redeploy and retry.

**Real fix (next round) — candidates.**
- Fresh event loop **per invocation** + explicitly reset anyio's worker thread
  pool (`anyio.to_thread.current_default_thread_limiter()` / recreate), instead
  of reusing `_loop`.
- Stop shutting down `langchain_core…_executor` in `handler()` — that
  `executor.shutdown(wait=False)` may be what poisons the shared pool; try just
  `cache_clear()` or nothing.
- Or move the pipeline to a synchronous httpx client (no anyio thread pool) for
  the serverless path.
- Or use `asyncio.Runner` (3.11+) with a fresh runner each call and no global
  executor reuse.

## A5. `< env, benign >` Pipeline function missing voice/vision env vars

**Finding.** `ps_1_cis_function` **has**: `MEMGRAPH_URI`, `ZC_LLM_ENDPOINT`,
`ZC_KB_ENDPOINT`, `ZC_KB_DOCUMENTS`, `ZC_CLIENT_ID`, `ZC_CLIENT_SECRET`,
`ZC_PROJECT_ID`, `ZC_REFRESH_TOKEN`, `ZC_ZIA_REFRESH_TOKEN`.
**Missing vs `pipeline_function/.env`**: `GROQ_API_KEY`, `HF_API_KEY`,
`ZC_VLM_ENDPOINT` — voice ASR fallback + vision/OCR only. **Text queries do not
need these.** Add them in the console (Serverless → Functions →
`ps_1_cis_function` → Configuration → Environment Variables) only when
voice/OCR on the deployed app is in scope.

Backend AppSail env is complete for its role (has `ZC_SIGNALS_PUBLISHER_URL`,
`ZC_ACCESS_TOKEN`, `ZC_NOSQL_TOKEN`, `GROQ_API_KEY`, `CORS_ALLOWED_ORIGINS`,
etc.). Missing only `HF_API_KEY` (voice).

## A6. `< client-side, not ours >` McAfee WebAdvisor blocks the deployed domain

**Symptom.** Chrome navigates to a `chrome-extension://…/site_status_block_page.html`
instead of the app; automation can't screenshot it.

**Cause.** The **McAfee WebAdvisor** browser extension flags the freshly-deployed
`catalystserverless.in` subdomain as unrated/unsafe. Nothing wrong with the site
(curl confirms 200 + correct SPA + assets).

**Fix.** Per-machine: click through the McAfee warning ("I understand the
risks / proceed"), or disable/allowlist the domain in the extension, or use a
browser without it for the demo. Reputation usually clears on its own over days.

## A7. `< process hygiene >` `catalyst deploy --only` colon-notation blocked

`catalyst deploy --only appsail:backend,client` was refused by the sandbox
command classifier. Use the plain forms one at a time:
`catalyst deploy --only appsail` then `catalyst deploy --only client`. Full
`catalyst deploy` and single-target `--only client` are fine.

## A8. `< info >` AppSail cold-start returns 503 briefly after deploy

After `catalyst deploy --only appsail`, `/api/health/` and `/api/auth/login`
return **503** for ~30–60 s while the container restarts, then recover. Poll
until non-503 before smoke-testing:
```
until [ "$(curl -s -o /dev/null -w '%{http_code}' https://backend-50043491738.development.catalystappsail.in/api/health/)" != "503" ]; do sleep 10; done
```

---

# B. Frontend bugs (all FIXED)

## B1. Evidence disappears when you switch pages and come back

**Root cause.** History turns were persisted as `{q, a}` only. `chatStore.loadHistory`
already read `h.evidence` / `h.visualization` — the **writers** never saved them.

**Fix.** Persist `{q, a, evidence, visualization}` (evidence capped 40/turn for
the NoSQL value-size limit) in **all** history writers:
`backend/job_dispatch.py` (`_local_pipeline_runner`), `pipeline_function/main.py`,
`functions/ps_1_cis_function/main.py` (the deployed one — see A3),
`functions/ps_1_cis_function/pipeline_function/main.py`. Commits `6a8fa60`,
`e1f4ebb`.

**Caveat.** Only turns created *after* the fix carry evidence; older turns
show answer text only (the data isn't there to backfill).

## B2. Can't type a space in corkboard text boxes

**Root cause.** `BoardCardFrame`'s `onKeyDown` handled Enter/Space to "select the
card" and called `e.preventDefault()`. A keydown from a child `<textarea>` /
`<input>` (free-note text, hypothesis resolve reason) **bubbles** up to the
frame div, so the space was preventDefault'd before it could be typed.

**Fix.** `if (e.target !== e.currentTarget) return;` at the top of the handler —
only act when the frame itself is focused. Commit `5359301`.

## B3. New Case dialog: crime_no / district accept only one character

**Root cause.** `Modal`'s focus-management `useEffect` depended on `onClose`.
`NewCaseDialog` passes a fresh inline arrow (`() => { reset(); onCancel(); }`)
every render. Each keystroke → `setState` → re-render → new `onClose` identity →
effect **cleanup runs** → `returnFocusRef.current?.focus?.()` yanks focus back to
the trigger, then the effect re-runs and re-focuses the *first* input (title).
Net effect: after one character in any non-first field, focus jumps away.

**Fix.** Hold `onClose` in a ref (`onCloseRef.current = onClose` each render);
the effect keys on `[open]` only. Commit `5359301`. This helps every `Modal`
consumer (also `ConfirmDialog`).

## B4. Entity Relation Network node clicks do nothing

**Root cause.** `NetworkGraph` bound its Cytoscape `tap` handler inside a
`useEffect` keyed on `[graphElements, onNodeClick, evidence]`. On mount
`cyRef.current` is still `null` (a ref write doesn't re-run the effect), and for
stable props the effect never re-ran, so the handler was never bound. Clicking a
node only triggered Cytoscape's built-in `:selected` styling (grow + highlight).

**Fix.** Bind the tap handler in the `cy={(cy) => …}` callback (the one place
`react-cytoscapejs` reliably hands over the live instance), reading latest props
via refs. Commit `6a8fa60`.

## B5. Victim node opens a FIR view ("Pin FIR as citation" on a victim)

**Root cause.** `NetworkGraph` coerced any node `type` not in
`['person','fir','location']` to `'fir'`, and `EntityDrawer` had no victim
branch. `'victim'` fell through to `FIRDetail`.

**Fix.** Added `'victim'` to `EntityType`, `NetworkGraph`'s allowed list, and a
`VictimDetail` panel (linked cases + accused, no pin). Commit `6a8fa60`.

## B6. FIR shown as a raw UUID (`a162ad7c-…`) everywhere

**Root cause.** FIR records have an 18-digit `crime_no`, but the pipeline's
evidence metadata didn't include it, so the UI fell back to the internal UUID.

**Fix.** Added `crime_no` to evidence metadata in
`pipeline_function/pipeline/retrieval/executor.py` (+ `functions/` mirror). New
`firLabel()` helper in `client/src/lib/utils.ts` renders `FIR <crime_no>`
everywhere, with a short uppercased 8-char fallback. Drawer hides a UUID
sub-line. Commit `6a8fa60`.

## B7. Hypothesis card = wall of text; "read more" had no button

**Root cause (v1).** Logging a hypothesis from chat seeded `statement` with the
*entire* Analytical Synthesis. **Root cause (v2).** The corkboard's
`HypothesisNoteCard` clamp had a faint, easy-to-miss toggle, and `BoardCardFrame`
grows to fit content (`minHeight`) so a long statement made a giant card.

**Fix.** New `detail` field on `HypothesisRecord` (≤ 8000 chars, optional) holds
the full source text; `statement` is a short gist (`summarizeAnalysis()`).
Corkboard card = gist only, hard-clamped 6 lines. Workspace "Working Hypotheses"
strip = gist + **"▾ Read full hypothesis"** → expands `detail`. Backend:
`shared/hypothesis_models.py` (+ mirror), both create request models +
endpoints. Commits `6a8fa60` (data model), `e1f4ebb` era.

## B8. No way to pin a suspect / the pin buttons were tiny

**Root cause.** The only pin action was a 13px grey icon on evidence cards
(`content_type: 'citation'`). **Nothing** created a `content_type: 'suspect'`
pin, and the person entity drawer (where a "pin suspect" belongs) could only be
opened from the workspace graph, never from chat.

**Fix.** Evidence cards show clickable **Accused chips** → person drawer →
**"Pin to Key Suspects"**. Entity drawer gained "Pin to Key Suspects" (person)
and "Pin FIR as citation" (FIR); accused name-chips are clickable. Pin icons
enlarged to labelled pills. Commit `6a8fa60`.

## B9. Corkboard page titled "persist-test"

**Cause.** Not a bug — the corkboard `<h1>` shows the **case title**, and a
leftover case from a timed-out e2e test script (`persist-test`, `c_431fe7c5`)
was the active case. Deleted it via the API. Also added an **"EVIDENCE BOARD"**
eyebrow above the case title for clarity. Commit `6a8fa60`.

---

# C. Backend / data-layer issues

## C1. `< partial fix + operational >` Case list changes on every refresh

**Symptom.** `/cases` shows a different set of cases across refreshes; sessions
appear/disappear. Verified: `/api/cases` is **stable within a few seconds** but
the list **changes over minutes** (`c_431fe7c5…` → `c_e6148eba` → `c_24736b40`
for `dysp1`).

**Root causes (two, compounding).**
1. **Shared account.** Multiple people testing as `dysp1` at once. `user_cases:{username}`
   is one JSON-array NoSQL key; `_add_case_to_user_index` /
   `_remove_case_from_user_index` lock only **per process** (`get_lock` →
   in-memory `asyncio.Lock`), not across AppSail instances or between the
   deployed backend and anyone's local backend. Concurrent create/delete stomp
   each other's index writes (last-writer-wins).
2. **NoSQL eventual consistency.** A just-written `case:{id}` /
   `session_meta:{id}` doc can briefly read back as absent, so `list_cases` /
   `list_case_sessions` (which do `[… for doc in docs if doc]`) drop that row
   for a refresh or two.

**Fixes.**
- (2) Commit `5359301`: `_nosql_get_stable()` in `backend/api/routes/cases.py`
  retries a `None` result twice (350 ms apart) in `list_cases` /
  `list_case_sessions`. Also tolerate a missing `last_activity_at` in the sort.
- (1) **Operational, not code:** each tester uses their own account —
  `dysp1` / `inspector1` / `si1` / `constable1`, all `demo1234`. A true code fix
  needs a conditional/CAS write on the NoSQL item, which the SDK version in use
  did not accept (noted in `catalyst_client.py` comments).

## C2. `< recurring >` `shared/` ↔ `functions/` mirror drift

Rule: every edit to `shared/*.py` must be copied into
`functions/ps_1_cis_function/shared/`. Backend-only files
(`backend/api/routes/*`, middleware) are **not** mirrored.

Drifts hit this session:
- `catalyst_client.py` — `transcribe_and_normalize` had diverged (old
  `ZIA_VOICE_LANGS` gate vs. new always-normalize). Resynced by
  `cp shared/catalyst_client.py functions/ps_1_cis_function/shared/` (no
  `pipeline_function.` prefix appears in that file, so a straight copy is safe).
- `hypothesis_models.py` — `detail` field; resynced by copy.
- `pipeline_function/pipeline/retrieval/executor.py` — `crime_no` metadata;
  applied to both.
- The **entrypoint** trap: see A3. `functions/ps_1_cis_function/main.py` is a
  divergent older shape (reads `job["result"]`, different loop handling) vs
  `pipeline_function/main.py`. They are **not** a simple prefix-mirror; reconcile
  the `history.append` / result handling in each by hand.

Parity check for prefix-mirrors:
```
diff <(sed 's/pipeline_function\.//g' shared/catalyst_client.py) \
     functions/ps_1_cis_function/shared/catalyst_client.py
```

## C3. `< dead code, harmless >` full-query cache short-circuit is never populated

`backend/job_dispatch.py` `dispatch_query_job` checks
`nosql_get(query_cache_key(query))` (`cache:full_query:{hash}`) and returns a
cached result without writing history. **Nothing writes that key** — only
`cache:ner_intent:{hash}` is written (by `pipeline_function/pipeline/cache.py`).
So the branch is dead; not the cause of any "instant answer" seen in testing
(that was the NER cache making the pipeline fast, or a warm container). If ever
wired, it must also append to `history:{sid}`.

---

# D. Local-dev gotchas (cost time this session)

- **Multiple `uvicorn` processes on :8001.** Restarting the backend without
  killing the old one → "address already in use", and stale processes can serve
  different data (mock vs real NoSQL). Clean restart:
  ```
  lsof -ti tcp:8001 | xargs kill -9 ; sleep 2
  pkill -9 -f "uvicorn backend.main" ; sleep 1
  source .venv/bin/activate
  nohup python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
  ```
  Backend runs **without `--reload`** — restart after every backend edit.
- **A Bash shell often starts with cwd `client/`.** `git` pathspecs and
  `npx vite`/`vitest`/`tsc` must run from the right dir. A `cd /…/CIS` earlier in
  a compound command changes cwd for later ones in the same call only. Check
  `pwd` if a command behaves oddly. Use absolute paths.
- **The session-start gitStatus banner has been stale** (wrong branch/commit).
  Trust `git branch --show-current` + `git log --oneline`.
- **`_should_use_mock_nosql()` raises in a deployed Catalyst context** if NoSQL
  config is missing (deliberate — no silent empty-store fallback in prod). Local
  falls back to `.nosql_mock_db.json`. If local `/api/cases` shows a wildly
  different set than deployed, local may be on the mock file.
- **e2e test scripts must clean up their cases** (`DELETE /api/cases/{id}`) — a
  script that times out before cleanup leaves junk cases (e.g. `persist-test`)
  in the shared NoSQL that show up for every tester.
- `timeout` (coreutils) is not on this macOS box — use a Python
  `asyncio.wait_for` or the Bash tool's own timeout instead.

---

# E. Gate commands (all green at `e1f4ebb`)

From `client/`:
```
npx tsc --noEmit          # exit 0
npx vitest run            # 23 passed
npm run build             # clean, ~844 modules (chunk-size warning is pre-existing)
```
From repo root:
```
source .venv/bin/activate && python -m pytest -q    # 126 passed
```
Backend restart after edits (no --reload). `shared/` edits → mirror to
`functions/ps_1_cis_function/shared/`.

---

# F. Triage order for "the deployed app is broken"

1. **`curl …/app/`** → 404 + `INVALID_URL`? → API Gateway is on with no rules →
   console → Cloud Scale → API Gateway → Disable (A1).
2. **`curl …/app/index.html`** → 200 but blank page? → check the asset `<script
   src>` hash vs your local `client/dist/index.html`; redeploy client if stale.
   Check `base: '/app/'` in `vite.config.ts`.
3. **Login works, queries hang?** → DevOps → Logs → Application →
   `ps_1_cis_function`, look for `cannot schedule new futures after shutdown`
   (A4) → `catalyst deploy --only functions` for a cold container as a
   stopgap.
4. **Login fails / "Invalid username or password" for everyone?** → backend
   AppSail lost its NoSQL config → Serverless → AppSail → backend →
   Configuration; confirm `ZC_*` tokens present; redeploy.
5. **Case list unstable?** → shared account; use separate demo logins (C1).
6. **503 right after a deploy** → cold start, wait 30–60 s (A8).
