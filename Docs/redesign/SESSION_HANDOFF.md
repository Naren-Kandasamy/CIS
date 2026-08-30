# Fresh-session handoff — CIS UI redesign

Read this first. `PHASE_HANDOFF.md` (same folder) has the phase-by-phase
detail; the approved plan is at
`/Users/vijayaraaghavanks/.claude/plans/https-www-bullet-in-board-online-ok-so-jaunty-neumann.md`.

Last updated: 2026-08-30 (through commit `9845585`).

---

## Status in one paragraph

A multi-phase UI redesign of the CIS (Conversational Crime Intelligence
System) frontend for Karnataka State Police on Zoho Catalyst. **Phases 0–7 of
the plan are complete**, plus post-plan additions: global dashboard restore,
graph-DB-backed entity relation network (per-case + officer-wide, with a
thin-graph overview fallback), the `:Person`→`:Accused` pipeline fix, and a
one-click "log this analysis as a hypothesis" bridge in chat. Everything lives
on branch **`feature/ui-redesign-v2`** and is **NOT merged to `main`** — the
user will say when. The app is runnable and demoable right now.

The redesign: log in → land in a room of manila **case folders** → open one →
a per-case **workspace** (persistent pinned citations, key suspects, a
freeform paper **corkboard** for hypotheses/evidence with red-yarn links) with
chat **sessions as "files"** inside the case. Plus a separate global
**`/dashboard`** with cross-case analytics. Aesthetic: aged-paper "Case File"
theme (kept and refined, never a full visual redesign).

---

## Standing rules (do not break these)

1. **Never merge to `main`.** Commit phase-wise / feature-wise on
   `feature/ui-redesign-v2` only. The user gives the merge go-ahead.
2. **The 3 env files stay separate** — `backend/.env`,
   `pipeline_function/.env`, `client/.env.production`. They hold live Catalyst
   credentials, are gitignored, and must NOT be merged into one. (User's
   words: "dont merge these 3 env into single they are meant to be separated".)
3. After a phase/feature: update `PHASE_HANDOFF.md`, then **ask the user to run
   `/compact`** before continuing.
4. `shared/` edits must be mirrored into `functions/ps_1_cis_function/`.
   Backend-only files (`backend/api/routes/*`, middleware) are **not** mirrored.

---

## Local dev

Both servers are usually already running:

- **backend** `:8001` — `curl -s localhost:8001/health` → `{"status":"ok"}`.
  Runs uvicorn **without `--reload`** — restart it after any backend edit:
  ```
  cd /Users/vijayaraaghavanks/Dev/CIS
  source .venv/bin/activate
  pkill -f "uvicorn backend.main"; sleep 2
  nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001 > /tmp/backend.log 2>&1 &
  ```
  If login starts returning **500**, the backend's Catalyst connection has
  wedged — restart it (fixes it).
- **client** `:5173/app/` — Vite dev server, hot-reloads.
- **login:** `dysp1` / `demo1234` (DySP Rao, role visible in sidebar footer).
- **test data:** cases `c_98e67a51` "Test Case Beta" (has pinned citations +
  a hypothesis + sessions) and `c_446e4f82` "Test Case Alpha".

`pytest` + `pytest-asyncio` + `playwright` (1.62.0) are all `pip install`-ed
into `.venv` now, and chromium binaries are provisioned
(`~/Library/Caches/ms-playwright/chromium-1234`). Run the E2E suite with
`.venv/bin/python tests/test_ui_redesign_playwright.py` (needs both dev
servers up). Current state: 6/8 scenarios green; scenarios 2 / 6 / 7
(create-case-via-dialog, pin-persist, board-persist) flake on this box
against the intermittently-500ing Catalyst dev backend — each does a
backend write then asserts a UI refetch inside a tight timeout. The
features themselves are verified working (manually in Phases 4/5, and
board add/drag re-verified this round). Restart the backend if you see the
500s (`GET /api/cases/:id/sessions` was the usual culprit).

---

## Repo topology & gotchas

- **Single git repo**, root `/Users/vijayaraaghavanks/Dev/CIS`. `client/` is a
  subdirectory (not a nested repo).
- **A Bash shell often starts with cwd `client/`.** `git` pathspecs and
  `npx vite`/`vitest` must run from the right dir — a `cd /…/CIS` earlier in a
  compound command changes cwd for later ones. Check `pwd` if a command fails
  oddly.
- The session-start **gitStatus banner has been stale** in past sessions
  (wrong branch / commit). Trust `git branch --show-current` +
  `git log --oneline`, not the banner.
- **Memgraph schema**: the investigation graph labels offenders **`:Accused`**
  (54 nodes, `[:ACCUSED_IN]`), **not `:Person`**. Also `:Victim` `[:VICTIM_IN]`,
  `:Account` `[:TRANSFERRED]`, `:Phone` `[:CALLED]/[:PINGED]`, `:Vehicle`,
  `:CellTower`, `:ANPRCamera`. `FIR` props: `id, date, crime_no, district,
  crime_type, modus_operandi, narrative`. The query pipeline's
  `MATCH (p:Person)-[r]->(f:FIR)` in
  `pipeline_function/pipeline/langgraph_router.py` matched nothing against this
  data — that was why the ER network showed only demo elements. **Fixed in
  `d62deed`** (uses `:Accused` now).
- **Basemap**: `CrimeMap.tsx` now uses plain OpenStreetMap tiles
  (`tile.openstreetmap.org`) — CARTO's Voyager basemap started stamping
  "API KEY REQUIRED" on every tile. The wrapper div's `filter: sepia(...)`
  still gives the aged-paper cast, so the look is preserved.
- **MCP Chrome screenshot bridge renders at a fixed size** (~1176×1027 or
  ~1389×868) regardless of `resize_window`. Don't trust it for responsive
  checks; the app has no responsive breakpoints anyway (desktop workstation
  tool by design — fixed 280px sidebar, `max-width:1600px` shell).
- **Chrome autofill fights the login form** in automation — clear each field
  (`cmd+a`, `Delete`) before typing.
- Reference skill folders (`impeccable-skill-v4.1.2/`,
  `ui-ux-pro-max-skill-2.15.0/`) are gitignored at repo root. `impeccable`
  scripts also at `~/.claude/skills/impeccable/scripts/` (`detect.mjs`,
  `palette.mjs`).

---

## Gates (run from `client/`)

```
npx vite build          # clean, ~840 modules
npx vitest run          # 20/20 (sse, chatStore, analysis)
npx oxlint src/         # exit 0 (1 pre-existing warning in ui/badge.tsx)
npx tsc --noEmit -p tsconfig.app.json   # exit 0 — now fully clean
```

`tsc` is **clean repo-wide** as of the lint sweep (`3c389e3`): a
hand-written `types/react-cytoscapejs.d.ts` plus small fixes to
`VoiceVisualizer.tsx` / `wavRecorder.ts` cleared the 4 old errors.

Backend: `source .venv/bin/activate && python -m pytest tests/ -q
-p no:cacheprovider` → **124 passed**. The old collection errors are gone
(`tests/conftest.py` `collect_ignore` for probe/e2e scripts) and
`test_query.py` / `test_zia_mocked.py` were updated to the current route
contracts. `ruff check .` is also clean (`ruff.toml`, narrow F/E9/B
ruleset). Standalone probe scripts still need `CATALYST_API_TOKEN` / live
services and are run by hand, not via `pytest tests/`.

Redesign-specific backend tests, all green:
`tests/test_cases_board_layout.py`, `tests/test_graph_endpoints.py`,
`tests/test_hypothesis.py` (case_id coverage added).

---

## What's built — routes & features

Router: `client/src/router.tsx`, `createBrowserRouter(…, {basename:'/app'})`.

| Route | Page | Notes |
|---|---|---|
| `/login` | `LoginPage` → `components/Login.tsx` | tokenized onto `styles/auth.css`, CSS focus/invalid states |
| `/cases` | `CasesIndexPage` | the folder room; manila `CaseFolder` tiles + open animation. Post-login lands here. |
| `/dashboard` | `GlobalDashboardPage` | **global** cross-case analytics — separate from any case. Sidebar nav "Dashboard". |
| `/cases/:caseId` | `CaseWorkspacePage` | per-case: `HypothesisStrip`, `CitationsTable`, `KeySuspectsList`, `WorkspaceGraphs` |
| `/cases/:caseId/board` | `CorkboardPage` | hand-rolled pan/zoom corkboard; persists via `case_board_layout:{id}` |
| `/cases/:caseId/sessions/:sessionId` | `SessionChatPage` | chat; `components/chat/*`; SSE via `lib/sse.ts` + poll recovery `lib/pollJob.ts` |

State: zustand — `authStore`, `casesStore`, `chatStore`, `boardStore`,
`entityStore`. API wrappers: `client/src/lib/api.ts`.

**CSS**: `client/src/index.css` = font/framework imports + 10 ordered
`@import`ed partials under `client/src/styles/` (`tokens.css` → `base.css` →
`theme-casefile.css` → `dashboard.css` → `entity-drawer.css` → `auth.css` →
`casefolder.css` → `sidebar.css` → `ui.css` → `board.css`) + `@theme inline` +
`@layer base`. `tokens.css` is the single source of truth: custom primitives
(`--bg-*`/`--accent-*`/`--text-*`), shadcn tokens `var()`-reference them. No
dark mode. Tailwind v4 CSS-first, **no `tailwind.config.js`**.

**Entity relation network** (both fed by real Memgraph data via
`backend/api/routes/graph.py`):
- `GET /api/cases/:id/graph` — per-case. Seed FIRs = that case's pinned
  citations + hypotheses + **FIR uuids scraped from the case's own session
  answers** (`history:{sid}`). One hop to `:Accused`/`:Victim`, district as a
  Location node. Collaborator-gated. Consumed by `WorkspaceGraphs.tsx`.
- `GET /api/graph` — officer-wide: union of those seeds across every case in
  `user_cases:{username}`. Accused linked to FIRs from ≥2 distinct cases get
  `data.shared` + `data.caseCount` (gold ring in the UI). **Thin-graph
  fallback**: <3 accused nodes → `_overview_layer` appends the top-6
  most-connected accused across the whole graph (faded, `data.overview`);
  response carries `overview` + `overview_note`. Consumed by
  `GlobalDashboardPage.tsx`.
- Graph DB unreachable → `{elements: [], degraded: true}` at HTTP 200;
  overview is best-effort and never fatal.
- `components/dashboard/NetworkGraph.tsx` `fallbackToDemo` prop: `true`
  (default, legacy callers) shows the built-in demo graph on empty data;
  `false` shows an empty-state. Its `cose` layout is deferred one frame with
  `cy.resize()` + fit-on-`layoutstop` — before that, an 80-node graph on a
  just-mounted panel piled every node at (0,0).

**Hypothesis suggestion from chat** (`e31c313`):
- `lib/analysis.ts` — `extractAnalysis(markdown)` pulls the
  `### Analytical Synthesis` prose out of a synthesis answer (strips
  `[FIR: …]` citations; returns `null` for profile/follow-up/error answers);
  `collectLinkedEntities(evidence)` unions FIR ids + `data.accused_ids`.
- `components/chat/HypothesisSuggestion.tsx` — a gold "Log this analysis as a
  hypothesis" affordance under a finished assistant message. Opens an inline
  editor pre-filled with the analysis text + removable entity chips; Save →
  `boardStore.addHypothesis` → `POST /api/cases/:id/hypotheses`. **Never
  auto-creates** — the officer edits and commits. Rendered by `MessageBubble`
  after the evidence panel.
- Restored-history messages (`{q,a}` only) carry no `evidence`; the chips now
  fall back to FIR ids parsed from the answer's `[FIR: …]` citations
  (`extractCitedFirIds`), so a reloaded turn still pre-fills links.

**Backend endpoints added across the redesign** (all in `backend/api/routes/`,
not mirrored): `PUT/GET /api/cases/:id/board/layout`,
`GET/POST /api/cases/:id/hypotheses`, `GET /api/investigation/hypothesis/:id/check`
(read back the last persisted check log), `PATCH /api/sessions/:id` `{title}`,
`GET /api/graph`, `GET /api/cases/:id/graph`. `shared/hypothesis_{models,
engine}.py` gained `case_id` + a `hypotheses_by_case:{id}` index (mirrored).
`backend/api/middleware/input_validator.py` gained a `/board/layout` exemption
from the 2 KB JSON body cap (`MAX_BOARD_LAYOUT_BYTES = 256 KB`).

---

## Commit history (this branch, newest first)

```
9845585 polish: drop plastic-sheen gradients, centre chat greeting, OSM basemap
f614c71 fix: board scatter overlap, persist hypothesis checks, restored-msg prefill
a3baf41 fix(board): always render corkboard canvas + toolbar; load once per case
e4c2a4e chore: reconcile functions/ pipeline mirror with pipeline_function/
3c389e3 chore: repo-wide lint sweep + pin ruff config
852d944 docs: SESSION_HANDOFF — hypothesis-suggestion feature + prioritised follow-ups
e31c313 feat(chat): "log this analysis as a hypothesis" — one-click from query
c212986 docs: SESSION_HANDOFF — seed broadening, overview, layout fix, ruff note
8454ad6 feat(graph): broaden ER-network seed + thin-graph overview fallback
2b560d7 docs: mark :Person->:Accused pipeline fix done in SESSION_HANDOFF
d62deed fix(pipeline): entity graph queries use :Accused, not :Person
5fd3c2a docs: fresh-session handoff (SESSION_HANDOFF.md)
5477e2a docs: handoff note for graph-DB-backed ER network
a712218 feat: real entity relation network — per-case + global cross-case
827f36c docs: handoff note for the restored global dashboard
c4e7686 feat: restore global analytics dashboard (separate from cases)
6186e8d docs: record Phase 7 commit hash in handoff
277be4c test: Phase 7 — verification sweep (Phases 1-6)
af844fe feat: Phase 6 — theme reconciliation
801db58 feat: Phase 5 — corkboard hypothesis/evidence board
646e31d feat: Phase 4 — case workspace + board persistence
a25f1d4 feat(client): Phase 3 — chat component extraction + drop App.tsx
db6247e feat(client): Phase 2 — chat state store + session-id/title contract
7992d08 feat(client): Phase 1 — router, app shell, case-folder landing
8819a56 refactor(client): Phase 0 — types module, SSE extraction, dead-code purge
```

---

## Open follow-ups

The A / B / C list below is **almost entirely done** as of `9845585`. The
working tree is clean. What's left is genuinely optional.

### Done this round (`3c389e3` → `9845585`)

- ✅ **A1** — repo-wide lint sweep committed (`3c389e3`): `ruff.toml` (narrow
  F/E9/B ruleset, `ruff check .` clean), dead imports + dead duplicate
  function stubs removed, `react-cytoscapejs.d.ts` + `VoiceVisualizer` /
  `wavRecorder` fixes → **`tsc` fully clean**, `tests/conftest.py`
  `collect_ignore` → `pytest tests/` runs 124 green, `test_query` /
  `test_zia_mocked` brought to current contracts. The risky bit
  (`ingest_extended_graphs.py` had its `synthetic_*` side-effect imports
  stripped) was caught and restored with `# noqa: F401`.
- ✅ **A2** — `functions/` pipeline mirror reconciled (`e4c2a4e`): the two
  missing `return`s in `run_langgraph_pipeline` restored (the deployed copy
  was skipping the history write), unused imports dropped. `langgraph_router`
  / `executor` / `synthesizer` mirrors now match canonical.
- ✅ **B1** — Playwright installed + run (`a3baf41`). 6/8 green; found & fixed
  the SSE poll-recovery scenario (its mock frames used a `{"type":…}` key the
  client parser ignores — real frames are `event:` + `data:` lines). See the
  Local-dev note above for the 2/6/7 flake.
- ✅ **B2** — `deriveBoardCards` scatter (`f614c71`): auto-placed cards now get
  their own sequential grid started below any user-placed cards; jitter
  tightened so a hash collision can't cause overlap.
- ✅ **B3** — hypothesis checks persist across reload (`f614c71`): new
  `GET /api/investigation/hypothesis/:id/check` reads back the already-stored
  `last_check:{id}`; `useHypotheses` hydrates `checkLogs` from it on mount.
- ✅ **B4** — restored-message entity prefill (`f614c71`): `extractCitedFirIds`
  recovers FIR ids from the answer's `[FIR: …]` citations when a reloaded turn
  has no `evidence` array.
- ✅ **A3 (bonus)** — empty corkboard had no toolbar → no way to add the first
  card. `CorkboardCanvas` + toolbar now always render (`a3baf41`), with an
  inline empty hint. Also fixed a race where `loadCase` re-fired on
  `cases.length` change and clobbered a just-added unsaved card.
- ✅ **C1** — plastic-sheen gradients removed from `.message-content` and
  `.dossier-stat-card` (`9845585`); laid-paper grain + soft vignette kept.
- ✅ **C2** — pre-conversation chat greeting is now centred
  (`.chat-messages--intro`), not pinned top-left over blank paper.
- ✅ **C3** — `CrimeMap` switched to plain OSM tiles; the "API KEY REQUIRED"
  CARTO watermark is gone, sepia cast preserved by the wrapper's CSS filter.

### Still open (optional)

- **B1 tail** — Playwright scenarios **2 / 6 / 7** (create-case-via-dialog,
  pin-persist, board-persist) flake on this box: each does a backend write
  then asserts a UI refetch inside a tight timeout, against the
  intermittently-500ing Catalyst dev backend. Worth a headed run with traces
  (`--headed`, `page.pause()`) on a stable backend; the features themselves
  work. `tests/test_ui_playwright.py` (the older pre-redesign suite) also
  hasn't been run this round.
- **C4** — no mobile/responsive layout. Deliberately out of scope (desktop
  workstation tool); net-new work if ever wanted.

---

## If you're picking this up

- Confirm branch (`git branch --show-current` → `feature/ui-redesign-v2`),
  `git status` clean, servers up (`curl -s localhost:8001/health`), log in
  `dysp1`/`demo1234`.
- Frontend work: gates from `client/` — `npx vite build`, `npx vitest run`
  (20/20), `npx oxlint src/` (0), `npx tsc --noEmit -p tsconfig.app.json` (0,
  now fully clean).
- Backend work: edit → restart uvicorn (no `--reload`) → `pytest` the touched
  suites (`python -m pytest tests/ -q` → 124) → live curl / browser.
  `ruff check .` should stay clean.
- Anything framed as "phase N" → follow the plan file; commit phase-wise;
  update `PHASE_HANDOFF.md`; ask for `/compact`.
- **Never merge to `main`** until the user says so.
