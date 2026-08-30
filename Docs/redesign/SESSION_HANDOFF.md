# Fresh-session handoff — CIS UI redesign

Read this first. `PHASE_HANDOFF.md` (same folder) has the phase-by-phase
detail; the approved plan is at
`/Users/vijayaraaghavanks/.claude/plans/https-www-bullet-in-board-online-ok-so-jaunty-neumann.md`.

Last updated: 2026-08-30 (through commit `e31c313`).

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

`pytest` + `pytest-asyncio` were `pip install`-ed into `.venv` (they weren't
there before). `playwright` is **not** installed and browser binaries aren't
provisioned — `tests/test_ui*_playwright.py` are CI-ready but can't run here.

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
- **CARTO basemap watermark**: the Leaflet map's Voyager tiles now show
  "API KEY REQUIRED / carto.com/basemaps/apikey" — CARTO gates that basemap
  behind a key. Cosmetic; markers/zoom/pan work. Same in the reference
  screenshots. Plain OSM tiles would drop the watermark and the sepia tint.
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
npx vitest run          # 18/18 (sse, chatStore, analysis)
npx oxlint src/         # exit 0, 0 findings
npx tsc --noEmit -p tsconfig.app.json
```

`tsc` is **not** clean repo-wide (~4 pre-existing errors:
`chat/VoiceVisualizer.tsx`, `dashboard/NetworkGraph.tsx` ×2 —
`react-cytoscapejs` has no types, `lib/wavRecorder.ts`). Gate = *newly
touched / new* files must be tsc-clean; those 4 files predate this work.

Backend: `source .venv/bin/activate && python -m pytest tests/ -q
-p no:cacheprovider`. ~99+ pass. Pre-existing failures unrelated to this
work: `test_query.py` ×3, `test_chaos`, `test_zia_mocked`, and ~6 collection
errors needing `CATALYST_API_TOKEN` / live services (`test_catalyst`,
`test_sdk`, `test_llm_json`, `test_shutdown`, …). Confirmed pre-existing via
`git stash`.

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
- Caveat: restored-history messages (`{q,a}` only) carry no `evidence`, so
  their entity pre-fill is empty (statement still seeds); fresh in-session
  responses get the chips.

**Backend endpoints added across the redesign** (all in `backend/api/routes/`,
not mirrored): `PUT/GET /api/cases/:id/board/layout`,
`GET/POST /api/cases/:id/hypotheses`, `PATCH /api/sessions/:id` `{title}`,
`GET /api/graph`, `GET /api/cases/:id/graph`. `shared/hypothesis_{models,
engine}.py` gained `case_id` + a `hypotheses_by_case:{id}` index (mirrored).
`backend/api/middleware/input_validator.py` gained a `/board/layout` exemption
from the 2 KB JSON body cap (`MAX_BOARD_LAYOUT_BYTES = 256 KB`).

---

## Commit history (this branch, newest first)

```
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

## Open follow-ups — start here in a fresh session

### A. Housekeeping (do first — the tree is not clean)

**A1. Commit or drop the parallel cleanup sweep already in the working tree.**
Not from the redesign sessions; left unstaged on purpose. `git status` shows
~30 modified files:
- a repo-wide `ruff --fix` pass (mostly unused-import removal + minor reformat)
  across `backend/`, `shared/`, `functions/`, `ingestion/`, `pipeline_function/`
- new `ruff.toml`
- new `client/src/types/react-cytoscapejs.d.ts` — a hand type-decl that
  **clears 2 of the 4 pre-existing `tsc` errors** (`NetworkGraph.tsx`)
- `client/src/components/chat/VoiceVisualizer.tsx` + `lib/wavRecorder.ts` —
  the other 2 pre-existing `tsc` errors, being fixed
- `tests/conftest.py` — adds `collect_ignore` for probe scripts so
  `pytest tests/` stops aborting on collection
- `tests/test_query.py`, `tests/test_zia_mocked.py` — someone started on the
  pre-existing failures

Review it, run the gates, and commit as its own `chore:` — or discard. Until
then any new commit risks dragging pieces of it in (stage explicit paths).

**A2. `functions/` mirror drift.**
`functions/ps_1_cis_function/pipeline_function/pipeline/langgraph_router.py` is
missing two `return` statements (~lines 758/770) vs the `pipeline_function/`
original — a pre-existing divergence, unrelated to the redesign. Reconcile the
mirror (diff the two files) so a future `shared/`-style mirror check is clean.

### B. Bugs / functional gaps

**B1. Playwright suites are authored but never run.**
`tests/test_ui_playwright.py`, `tests/test_ui_redesign_playwright.py` (8
scenarios: folder landing, dialog create, session URL shape, query→evidence,
pin persist, board drag persist, SSE poll-recovery). `playwright` isn't in
`.venv` and no browser binaries — `pip install playwright && playwright
install chromium`, start both servers, then `python tests/test_ui_redesign_playwright.py`.

**B2. Corkboard `deriveBoardCards` scatter** can overlap on hash collisions for
3+ un-placed cards. Harmless once dragged, but a real first-load annoyance.
`stores/boardStore.ts` — the `scatter()` FNV-hash placement.

**B3. Hypothesis-`check` logs are session-transient.** The corkboard shows a
`HypothesisCheckLog` after you click Check, but there's no server list endpoint
to re-read them on reload. Needs a `GET /api/investigation/hypothesis/:id/checks`
(or fold the last check into the record).

**B4. Hypothesis-suggestion entity pre-fill is empty on restored messages.**
`history:{sid}` stores only `{q, a}` — no evidence — so a page-reloaded answer's
"Log as hypothesis" seeds the statement but no entity chips. Options: persist a
trimmed evidence list per turn, or in `HypothesisSuggestion` fall back to
regexing FIR uuids out of the answer's `[FIR: …]` citations.

### C. Polish / nice-to-have

**C1. Chat bubble "plastic sheen".** `.message-content` in
`styles/theme-casefile.css` layers a heavy diagonal highlight gradient that
reads as glossy plastic, not paper. Soften or drop the
`linear-gradient(100deg …)` / `linear-gradient(-75deg …)` fold layers.

**C2. Chat greeting gap** — large empty space above the first message (noted
since Phase 1).

**C3. CARTO basemap watermark** on the Leaflet map (see gotchas) — swap the
tile URL to plain OSM to lose the "API KEY REQUIRED" text, at the cost of the
sepia Voyager tint.

**C4. No mobile/responsive layout.** Deliberately out of scope (desktop
workstation tool); would be net-new work if ever wanted.

### Done this round (for reference)

- ✅ `:Person`→`:Accused` in the pipeline graph builders (`d62deed`).
- ✅ ER network seed broadened to include session-query FIRs + thin-graph
  overview fallback (`8454ad6`).
- ✅ `NetworkGraph` `cose` layout no longer piles nodes at (0,0) (`8454ad6`).
- ✅ "Log this analysis as a hypothesis" chat bridge (`e31c313`).

---

## If you're picking this up

- Confirm branch (`git branch --show-current` → `feature/ui-redesign-v2`),
  check `git status` (expect the A1 sweep unless it's been committed), servers
  up (`curl -s localhost:8001/health`), log in `dysp1`/`demo1234`.
- Frontend work: gates from `client/` (build / vitest / oxlint / tsc-clean on
  touched files).
- Backend work: edit → restart uvicorn (no `--reload`) → `pytest` the touched
  suites → live curl / browser.
- Stage **explicit paths** when committing until A1 is resolved — don't
  `git add -A`.
- Anything framed as "phase N" → follow the plan file; commit phase-wise;
  update `PHASE_HANDOFF.md`; ask for `/compact`.
