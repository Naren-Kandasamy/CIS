# Investigation Workspace Redesign — Phase Handoff

Living document. Updated at every phase boundary. Read this first after any
context reset, then the plan file for full detail.

- **Branch:** `feature/ui-redesign-v2` (never merge to `main` until told)
- **Plan file:** `/Users/vijayaraaghavanks/.claude/plans/https-www-bullet-in-board-online-ok-so-jaunty-neumann.md`
- **Local servers:** backend `:8001`, client `:5173/app/`, login `dysp1` / `demo1234`
- **Client gates:** `cd client && npx vite build` + `npx vitest run` (pre-existing
  `tsc` errors in files not yet touched are expected — the repo was never tsc-clean;
  only check that *newly touched* files are clean).
- **Env files** (gitignored, already in place): `backend/.env`, `pipeline_function/.env`,
  `client/.env.production`.
- Reference skill folders live at repo root (`impeccable-skill-v4.1.2/`,
  `ui-ux-pro-max-skill-2.15.0/`) and are gitignored. `impeccable` skill also
  installed at `~/.claude/skills/impeccable/`.

---

## The goal (what we're building)

Log in → land in a room full of **manila case folders** → open one (folder
animation) → a real **per-case workspace** (persistent citations, key suspects,
a freeform **paper corkboard** for hypotheses/evidence with red-yarn links)
with chat **sessions as "files"** inside the case. Keep and refine the existing
aged-paper "Case File" theme — no full visual redesign. Backend work is in scope
(extend the `case_board` API for persistence).

Design decisions locked with the user:
1. react-router + per-case routes + zustand store.
2. Board = LIGHT paper corkboard (Kingsman image is mood only, not dark).
3. Keep & refine the Case File theme; tokenize `Login.tsx`.
4. Backend in scope: `case_board_layout` doc + hypotheses re-keyed to `case_id`.
5. Cases index = big manila folders with an open animation revealing session sheets.

---

## Phase status

| Phase | State | Summary |
|---|---|---|
| 0 — Foundation | ✅ done (`8819a56`) | types module, SSE extraction, dead-code purge |
| 1 — Router + shell + folder grid | ✅ done (`7992d08`) | routes, stores, AppShell, folder room, chat page |
| 2 — State migration | ⏳ next | chat `messagesBySession` → `chatStore`; session-id contract |
| 3 — Chat extraction | pending | split SessionChatPage into chat/* components; delete App.tsx |
| 4 — Case Workspace + backend persistence | pending | `case_board_layout` API, `hypotheses_by_case`, per-case workspace |
| 5 — Corkboard | pending | React Flow spike → freeform board, yarn edges, retire HypothesisWorkspace |
| 6 — Theme refinement | pending | token reconciliation, Login tokenize, index.css split, board tokens |
| 7 — Verification | continuous | Playwright + backend tests + impeccable audit |

---

## Phase 0 — DONE (`8819a56`)

**New — `client/src/types/`**: `entities.ts` (SelectedEntity/LinkedNode/EntityType),
`case.ts` (Case/SessionMeta/HistoryTurn), `chat.ts` (Message/EvidenceItem/
Visualization/PIPELINE_STEPS/QueryLanguage), `hypothesis.ts`, `board.ts`
(BoardCard/BoardLayout/PinnedItem), `api.ts` (response envelopes), `index.ts`.
`hooks/useEntityDrawer.ts` re-exports the promoted entity types.

**New — `client/src/lib/`**:
- `sse.ts` → `streamQuery(params, handlers)`: the hand-rolled SSE frame parser +
  cross-read buffer + `job_id` capture + AppSail cut-off recovery flag, lifted
  verbatim from App.tsx behind `{onJob,onProgress,onEvidence,onVisualization,
  onToken,onDone,onError,onUnauthorized}`. Returns `{jobId, sawTerminalEvent}`.
- `pollJob.ts` → `pollForCompletedJob(jobId, token, ...)`.
- `api.ts` → `apiFetch<T>()` + typed wrappers for every endpoint (login, cases,
  sessions, board, board/layout, hypotheses, warmup, transcribe). `ApiError`
  carries `.status`.
- `sse.test.ts` → 8 Vitest cases, all green.

**Changed**: `App.tsx` calls `streamQuery`/`pollForCompletedJob` (message-patch
reducer bodies unchanged). `tsconfig.app.json` gains `ignoreDeprecations: "6.0"`.
`package.json` gains `vitest` + `test`/`test:watch`/`typecheck` scripts; drops
unused `@fontsource-variable/geist`; adds `react-router-dom` + `zustand` (first
used in Phase 1, added here for lockfile coherence).

**Deleted (~30 files)**: shadcn dashboard scaffold (`app-shell/-sidebar/-header/
-breadcrumbs/-shared`, `nav-group/-user`, `dashboard.tsx`, `dashboard-skeleton`,
`latest-change`, `logo`, `indicator`, `csat-responses-chart`,
`first-reply-time-chart`, `support-activity`, `team-on-duty`,
`dashboard/DonutChart`, `dashboard/TrendChart`, `formater.ts`), orphaned
`ui/` primitives (`sidebar`, `sheet`, `collapsible`, `breadcrumb`, `avatar`,
`kbd`, `skeleton`, `dropdown-menu`), `hooks/use-mobile.ts`, `src/App.css`,
`src/assets/*`.

**impeccable baseline** (`detect.mjs`): pre-existing `animate-bounce` (App.tsx),
side-tab borders at `HypothesisWorkspace.tsx:305` (retired Phase 5),
`index.css` sidebar `border-right:3px` (folder-spine, intentional) and entity
drawer `border-left:3px` (Phase 6).

---

## Phase 1 — DONE (`7992d08`)

**Routing** — `client/src/router.tsx`, `createBrowserRouter(..., {basename:'/app'})`:
`/login` · `/cases` · `/cases/:caseId` · `/cases/:caseId/board` (stub) ·
`/cases/:caseId/sessions/:sessionId` · `*`→NotFound. `RequireAuth`
(`components/auth/`) guards everything under `AppShell`. `main.tsx` →
`<RouterProvider>`.

**Stores** — `client/src/stores/` (zustand):
- `authStore.ts` — `{token, displayName, role, login(), logout()}`, sessionStorage
  keys unchanged (`ps1_auth_token`/`ps1_display_name`/`ps1_role`). `getToken()`
  for non-React reads.
- `casesStore.ts` — `{cases, sessionsByCase, loaded, fetchCases, fetchSessions,
  createCase, createSession, deleteCase, deleteSession, touchCase}`. Optimistic
  delete with rollback.
- `entityStore.ts` — `{entity, open(), close()}` for the app-level drawer.

**Shell / nav**:
- `layouts/AppShell.tsx` — `.ambient-bg` + `.app-container` + `<CaseDrawerSidebar>`
  + `.shell-main` `<Outlet>` + app-level `<EntityDrawer>` + `/api/warmup`
  heartbeat (4-min interval, moved from App.tsx).
- `components/nav/CaseDrawerSidebar.tsx` — brand, All cases / New case, and for
  the routed `:caseId`: case title, Workspace + Evidence board links, sessions
  tree (NavLinks + New session + delete), sign out. Owns its own NewCaseDialog +
  ConfirmDialog instances.

**Pages** — `client/src/pages/`:
- `LoginPage.tsx` — wraps existing `components/Login.tsx`; on success →
  `authStore.login` → `navigate('/cases')`. Redirects to `/cases` if already authed.
- `CasesIndexPage.tsx` — the folder room. Grid of `CaseFolder`, a dashed
  "＋ New case" folder, `EmptyState` when none, NewCaseDialog + ConfirmDialog.
  Prefetches sessions for the first 6 cases (folder sheet previews).
- `CaseWorkspacePage.tsx` — header + (if 0 sessions) EmptyState "Start first
  session" else `<DashboardPanel />` (unchanged; Phase 4 rewires it per-case).
- `SessionChatPage.tsx` — **the chat, lifted out of App.tsx**, bound to
  `:sessionId`. Local `messages` state (Phase 2 → chatStore), `getSession` load,
  `streamQuery` submit + `pollForCompletedJob` recovery, voice
  (`wavRecorder` + `VoiceVisualizer`), feedback POST, evidence cards → `entityStore.open`.
  Refreshes `fetchSessions` after the first turn to pick up the server-set title.
- `CorkboardPage.tsx` — stub EmptyState (Phase 5).
- `NotFoundPage.tsx`.

**Components — `client/src/components/`**:
- `common/Modal.tsx` — dialog primitive (Escape, click-outside, focus in/return).
- `common/ConfirmDialog.tsx`, `common/EmptyState.tsx`.
- `cases/NewCaseDialog.tsx` — title (required) + crime_no + district.
- `cases/CaseFolder.tsx` — manila folder; on activate: lift + cover rotate
  `-116deg` about top edge + sheets fan up (`--i` stagger), then
  `navigate('/cases/:id')` after 420ms (90ms + no transform under
  `prefers-reduced-motion`). Keyboard Enter/Space.

**CSS** — `client/src/index.css` now `@import`s three partials:
`styles/ui.css` (buttons `.btn-primary/-danger/-ghost`, `.modal-*`, `.dialog-*`,
`.empty-state*`, `.shell-main`, `.workspace-page/-head`, `.chat-container` height
fix), `styles/sidebar.css` (`.drawer-*`), `styles/casefolder.css`
(`.cases-room`, `.cases-grid`, `.case-folder` + animation). New token
`--accent-primary-hover: #6f211c` in `:root`.

**Verified live in Chrome**: login → `/cases` folders → open folder → workspace →
open session → ran "list recent theft cases in Belagavi" → full 7-step pipeline,
streamed answer, 11-citation evidence card. Zero console errors.

**Known cosmetic debt (Phase 6)**: folders read a little flat; chat greeting has
a large empty gap; `App.tsx` orphaned (delete end of Phase 3).

---

## Phase 2 — NEXT. Goal

Move the chat's per-session message state out of the component into a store, and
adopt the server-issued session-id contract. This is the riskiest state change —
the SSE loop patches a message ~10×/query.

**Do:**
1. `client/src/stores/chatStore.ts` (zustand):
   - `messagesBySession: Record<string, Message[]>`, `feedbackStatus`,
     `activeCorrectionId`, `correctionExplanation` (or keep the last two local).
   - `loadHistory(sessionId)` — `getSession`, hydrate greeting/restored.
   - `sendQuery(sessionId, caseId, text, lang, token)` — calls `lib/sse.ts` with
     handlers wired to `patchMessage(sessionId, msgId, fn)`; recovery via
     `lib/pollJob.ts`; `touchCase` + first-turn `fetchSessions`.
   - `patchMessage`, `submitFeedback`.
   - Use `useChatStore.getState().patchMessage(...)` inside SSE handlers — no
     stale closures (this is the whole point vs. the old
     `updateSessionMessages(prev=>…)` that captured `targetSessionId`).
2. Rewrite `pages/SessionChatPage.tsx` to be a thin consumer of `chatStore`
   (selector-scoped so a token stream re-renders only the one message list).
   Keep the exact JSX/markup for now (Phase 3 splits it).
3. Session-id contract:
   - Frontend already uses the server `s_` id from `POST /api/cases/:id/sessions`
     (Phase 1 does this). Grep `crypto.randomUUID` for stray session minting
     (feedback `event_id` legitimately keeps it).
   - Read `pipeline_function/pipeline/langgraph_router.py` + the job-completion
     writer: confirm `history:{s_…}` is persisted and `session_meta.title` is set
     on the first turn. If title is NOT set server-side, add it in the job writer
     (preferred) or add `PATCH /api/sessions/{sid}` `{title}` and call it after
     the first successful turn.
4. Add `client/src/stores/chatStore.test.ts` — token-parity: feed a recorded SSE
   stream through `sendQuery` (mock `lib/utils.fetchWithRetry`) and assert the
   final message content/evidence/visualization match; assert a no-terminal
   stream recovers via the poll.

**Risk / mitigation:** keep the message-patch reducer bodies byte-identical to
Phase 1's `patch(...)` calls; migrate only where the state lives. Verify live
(same query flow) + the new store test before committing.

**Entry points:** `pages/SessionChatPage.tsx` (current chat logic to move),
`lib/sse.ts` + `lib/pollJob.ts` (unchanged), `stores/casesStore.ts` (pattern to
mirror), `backend/api/routes/sessions.py` + `cases.py` (session-id / title),
`pipeline_function/pipeline/langgraph_router.py` (history + title writer).

**Exit criteria:** chat works identically; `messagesBySession` lives in
`chatStore`; `vite build` + `vitest` green; new `chatStore.test.ts` passes;
committed as `feat(client): Phase 2 — chat state store + session-id contract`.
Then update this file's Phase 2 section, mark Phase 3 as next, and stop for /compact.
