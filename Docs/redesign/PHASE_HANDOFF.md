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
| 2 — State migration | ✅ done (`db6247e`) | chat `messagesBySession` → `chatStore`; session-id + title contract |
| 3 — Chat extraction | ✅ done | split SessionChatPage into `components/chat/*`; `useVoiceRecorder`; deleted App.tsx |
| 4 — Case Workspace + backend persistence | ✅ done | `case_board_layout` API, `hypotheses_by_case`, `boardStore`, persistent per-case workspace, chat "Pin to board" |
| 5 — Corkboard | ✅ done | hand-rolled pan/zoom board, draggable pinned cards, red-yarn links, hypothesis check/resolve inline, retired HypothesisWorkspace + DashboardPanel |
| 6 — Theme refinement | ⏳ next | token reconciliation in `index.css`, `Login.tsx` tokenization, split `index.css` into `styles/*`, delete 4 orphaned analytics charts, `--text-tertiary` contrast |
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

## Phase 2 — DONE

**New — `client/src/stores/chatStore.ts`** (zustand): owns
`messagesBySession: Record<string, Message[]>`, `loadingBySession`,
`feedbackStatus`. Actions:
- `loadHistory(sessionId)` — reset to greeting, then `getSession` → hydrate
  `restored` + `hist-N-u/-a` turns (byte-identical to the old effect body).
- `patchMessage(sessionId, id, fn)` — the single message-patch reducer.
- `sendQuery({sessionId, caseId?, text, language, token, onUnauthorized?})` —
  pushes user + assistant placeholder, runs `streamQuery` with handlers wired to
  `get().patchMessage(...)` (no stale closures), `pollForCompletedJob` recovery,
  then `touchCase` + first-turn `renameSession` → `fetchSessions`. Reducer bodies
  copied verbatim from Phase 1's `patch(...)` calls. `wasFirstTurn` is derived
  (`!messages.some(m => m.role === 'user')`) — the `isFirstTurnRef` is gone.
- `submitFeedback({sessionId, item, verdict, explanation, queryText, officerId})`
  — the `/api/feedback/correction` POST; returns `boolean` ok.

**Changed — `pages/SessionChatPage.tsx`**: now a thin `chatStore` consumer.
Selector-scoped reads (`messagesBySession[sessionId]`, `loadingBySession`,
`feedbackStatus`). Local state kept: `inputValue`, `voiceLanguage`,
`activeCorrectionId`, `correctionExplanation`, voice/recording. **Exact JSX
preserved** (Phase 3 splits it). `handleSubmit` → `sendQuery`; `handleFeedbackSubmit`
→ `submitFeedback`.

**Session-id + title contract:**
- `crypto.randomUUID` audit: only legit uses remain — `chatStore` message ids
  (user + assistant placeholder) and the feedback `event_id`. No session minting.
- **New `PATCH /api/sessions/{session_id}` `{title}`** in `backend/api/routes/sessions.py`
  (`SessionPatchRequest`, min 1 / max 120 chars, `_require_collaborator`,
  re-read under `get_case_lock`). `lib/api.ts` → `renameSession(sessionId, title)`.
  `chatStore.sendQuery` calls it on the first turn with `text.trim().slice(0, 80)`,
  then `fetchSessions` so the sidebar shows the query as the session label.
- **`history:{session_id}` local-dev fix** — `backend/job_dispatch.py`
  `_local_pipeline_runner` was mutating an in-memory `session_state["history"]`
  (in `{role,content}` shape) that was **never written back**, so local sessions
  always reloaded empty. Now appends `{q, a}` to `history:{session_id}` capped at
  10 turns — matching the Signals path in `pipeline_function/main.py`. Production
  path was already correct; `functions/ps_1_cis_function/job_dispatch.py` is a
  41-line status-helper shim with no runner, so no mirror change.

**Test — `client/src/stores/chatStore.test.ts`** (5 cases, mocks `../lib/utils`
`fetchWithRetry`): SSE token/evidence/visualization parity onto the assistant
message; no-terminal stream → status-poll recovery; multi-turn history
accumulation; `loadHistory` hydrate + empty-history greeting fallback. All green
(13 total with `sse.test.ts`).

**Verified live in Chrome**: login → folder → new session (`+`) → query → full
7-step pipeline through `chatStore` → answer + 11-citation evidence → Confirm
feedback records → sidebar session relabels to the first query → **reload
restores the transcript** ("Restored session history." + turns). Zero console
errors. Known Phase-1 debt still open: a cold deep-link to a session URL leaves
the sidebar without case context until `/cases` is visited (casesStore empty).

**Gate status:** `npx vitest run` 13/13 · `npx vite build` clean · touched files
tsc-clean. Backend was restarted (no `--reload`) to pick up the two backend
changes — restart it after any future backend edit:
`source .venv/bin/activate && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001`.

---

## Phase 2 — original goal (for reference)

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

---

## Phase 3 — DONE

Pure structural refactor. `pages/SessionChatPage.tsx` went from ~460 lines of
inline JSX to a ~40-line container; the chat UI now lives in `components/chat/*`
and the mic flow in a hook. **No store or API changes.** Class names unchanged
(`styles/*` / Case File CSS still match). `client/src/App.tsx` deleted (`App.css`
was already gone). Nothing imported `App.tsx` since Phase 1.

**New files:**
- `hooks/useVoiceRecorder.ts` — `{ isRecording, isPaused, isTranscribing,
  toggleRecording, togglePause, getAnalyser }`; takes `{ language, onTranscript }`.
  Body lifted verbatim from the old page's mic/transcribe/pause handlers.
- `components/chat/ChatView.tsx` — `.chat-container` layout: `<MessageList>` +
  `<InputBar>`. Props: `messages`, `sessionId`, `isLoading`, `onSend`.
- `components/chat/MessageList.tsx` — `.chat-messages`, maps `<MessageBubble>`,
  owns `messagesEndRef` autoscroll **and** the lifted `activeCorrectionId` /
  `correctionExplanation` state (one correction box open at a time, preserved).
  Selects `feedbackStatus` / `submitFeedback` from `chatStore`, `displayName`
  from `authStore`, `open` from `entityStore`. Builds the `EvidenceFeedback`
  bundle passed down through MessageBubble → EvidencePanel → EvidenceCard.
- `components/chat/MessageBubble.tsx` — one `.message` row: avatar +
  `<PipelineProgress>` + `.message-content` (markdown / streaming skeleton) +
  `<EvidencePanel>` when `message.evidence?.length`.
- `components/chat/PipelineProgress.tsx` — the status pill + `PIPELINE_STEPS`
  stepper; renders `null` when no `status`.
- `components/chat/EvidencePanel.tsx` — the `<details className="evidence-card">`
  block + grid; exports the `EvidenceFeedback` type. Keys feedback state by
  `item.edge_id || item.fir_id` exactly as before.
- `components/chat/EvidenceCard.tsx` — one `.evidence-item` citation card;
  `openEntity({ type: 'fir', ... })` on click / Enter / Space; hosts
  `<FeedbackControls>`.
- `components/chat/FeedbackControls.tsx` — `.feedback-controls`: "recorded" pill,
  Confirm / Correct buttons, correction textarea. Controlled — all state + the
  submit handler come from props (owned by MessageList).
- `components/chat/InputBar.tsx` — `.input-area` + recording strip + `.input-box`
  form. Owns its own `inputValue` + `voiceLanguage` (default `'kn'`) and uses
  `useVoiceRecorder`. Guards `!text.trim() || disabled || isTranscribing`, then
  `onSend(text, language)`.

**`pages/SessionChatPage.tsx` (rewritten):** reads `:caseId` / `:sessionId`,
selects `messages` / `isLoading` / `loadHistory` / `sendQuery` from `chatStore`
and `token` / `logout` from `authStore`. `loadHistory(sessionId)` in a
`useEffect` on id change. `handleSend(text, language)` → `sendQuery({ sessionId,
caseId, text, language, token, onUnauthorized: logout })`. Renders `<ChatView>`.

**Gates:** `npx vite build` clean · `npx vitest run` 13/13 · touched files +
new files tsc-clean (`tsconfig.app.json` error count unchanged at 37 — all
pre-existing; `components/chat/VoiceVisualizer.tsx:10` TS2554 predates this phase
and that file was not touched) · `oxlint src/` — no new findings.

**Live-verified in Chrome** (existing session in Test Case Beta): history
restored on open → fresh query streamed through the extracted `PipelineProgress`
stepper (7 steps) and streaming skeleton → answer rendered → `EvidencePanel`
(10 citations) → `FeedbackControls` "Confirm" → "✓ Feedback recorded
(confirmed)" → page reload restores the transcript **including the new turn**.
Zero console errors.

**Commit:** `feat(client): Phase 3 — chat component extraction + drop App.tsx`.

---

## Phase 3 — original goal (for reference)

Split `pages/SessionChatPage.tsx` (~330 lines of inline JSX) into
`components/chat/*`, preserving every behavior, and **delete the orphaned
`client/src/App.tsx`** (nothing imports it since Phase 1; auth/shell now live in
`AppShell` + `authStore`).

**Do:**
1. `pages/SessionChatPage.tsx` stays the route entry — reads `:sessionId`,
   subscribes `chatStore`, `loadHistory` on mount — but renders `<ChatView>`.
2. New `components/chat/`:
   - `ChatView.tsx` — the `.chat-container` layout (message list + input area).
   - `MessageList.tsx` — maps messages, owns `messagesEndRef` autoscroll.
   - `MessageBubble.tsx` — avatar + `ReactMarkdown` + `QUERY`/`FIELD REPORT`
     stamp; hosts `PipelineProgress` + `EvidencePanel`.
   - `PipelineProgress.tsx` — the `PIPELINE_STEPS` stepper (status pill + dots).
   - `EvidencePanel.tsx` / `EvidenceCard.tsx` — the `<details>` evidence block;
     card opens `entityStore.open`; hosts `FeedbackControls`.
   - `FeedbackControls.tsx` — Confirm / Correct + explanation textarea; calls
     `chatStore.submitFeedback` (move `activeCorrectionId` /
     `correctionExplanation` local state in here).
   - `InputBar.tsx` — Paperclip, text input, EN/HI/KN select, Mic, Send.
   - `hooks/useVoiceRecorder.ts` — lift the `wavRecorder` mic/transcribe/pause
     flow out of the page; keeps rendering `components/chat/VoiceVisualizer.tsx`.
3. Delete `client/src/App.tsx` and `client/src/App.css` if still present. Grep
   for any lingering import first.
4. Playwright parity (or live Chrome): progress pill appears→hides, evidence
   renders, feedback records, SSE "stream cut → poll recovers" path.

**Risk:** pure structural refactor — no store/API changes. Keep prop-drilling
shallow (pass `sessionId` + store selectors down, or let leaf components select
from `chatStore` themselves). Don't change class names — `styles/*` and the
Case File CSS target them.

**Entry points:** `pages/SessionChatPage.tsx` (the JSX to split),
`stores/chatStore.ts` (already the data source), `components/chat/VoiceVisualizer.tsx`,
`lib/wavRecorder.ts`, `App.tsx` (delete target).

**Exit criteria:** chat identical; `App.tsx` gone; `vite build` + `vitest`
green; committed `feat(client): Phase 3 — chat component extraction + drop App.tsx`.
Update this file, mark Phase 4 next, stop for /compact.

---

## Phase 4 — DONE

Per-case **Case Workspace** now reads **persistent** server state instead of the
last query's in-memory visualization.

**Backend — `backend/api/routes/cases.py`:**
- `GET /api/cases/{id}/board/layout` → `{ cards: [] }` (empty if absent).
- `PUT /api/cases/{id}/board/layout` `{ cards }` — full replace under
  `get_case_lock` + `_require_collaborator`, writes `case_board_layout:{id}` =
  `{ cards, updated_at, updated_by }`. `BoardCardModel` caps enforced (422):
  `kind` enum, `color` regex `^(#hex|word|var(--x))$`, `text` ≤ 2000,
  `connections` ≤ 50, `cards` ≤ 200, float coords. Field name `refId` matches the
  client JSON verbatim.
- `GET /api/cases/{id}/hypotheses` → `list_hypotheses_by_case(id)`.
- `POST /api/cases/{id}/hypotheses` `{ statement, linked_entity_ids, fir_id? }` —
  injects `case_id`; `fir_id` falls back to `case_id` when none given.
- `delete_case` `delete_tasks` gained `case_board_layout:{id}` +
  `hypotheses_by_case:{id}`.
- `shared/hypothesis_models.py`: `case_id: Optional[str] = None` on
  `HypothesisRecord`. `shared/hypothesis_engine.py`: `create_hypothesis` also
  writes the `hypotheses_by_case:{case_id}` index (locked RMW, factored into
  `_add_to_index`); new `list_hypotheses_by_case` (factored `_list_by_index`).
  `backend/api/routes/hypothesis.py`: `HypothesisCreateRequest.case_id` optional,
  passed through — the 4 `/api/investigation/hypothesis*` routes stay
  byte-compatible.
- **Mirror**: `functions/ps_1_cis_function/shared/hypothesis_{models,engine}.py`
  copied (`diff -q` clean). `cases.py` / `hypothesis.py` are backend-only, not
  mirrored. `catalyst_client.py` mirror drift is pre-existing, not touched here.
- Verified by curl against the live backend: empty→PUT→GET layout round-trip,
  422 on bad `kind`, hypothesis create + list + `case_id` echoed, `delete_case`
  runs the new deletes. (`_require_collaborator` 500s on a *reload after delete*
  — pre-existing fragility shared by every case route, not introduced here.)

**Frontend:**
- `client/src/stores/boardStore.ts` (new, zustand): `pinsByCase`, `layoutByCase`,
  `hypothesesByCase`, `loadingByCase`; `fetchBoard/fetchLayout/fetchHypotheses`,
  `loadCase` (parallel), `pin` (optimistic append + re-read), `putLayout`
  (optimistic, Phase 5 consumer), `addHypothesis`. `lib/api.ts` gained
  `createCaseHypothesis`.
- `pages/CaseWorkspacePage.tsx` rewritten: calls `loadCase(caseId)`; renders
  `HypothesisStrip` + `CitationsTable` + `KeySuspectsList` + `WorkspaceGraphs`
  from persisted pins/hypotheses; "Nothing pinned to this case yet" EmptyState;
  header "Evidence board" link. No longer imports `DashboardPanel`.
- `client/src/components/workspace/` (new): `CitationsTable` (pins
  `content_type==='citation'` → rows → `entityStore.open`), `KeySuspectsList`
  (`'suspect'` pins), `HypothesisStrip` (list + inline add via
  `boardStore.addHypothesis`), `WorkspaceGraphs` (derives cytoscape elements +
  leaflet markers client-side from pinned FIRs/suspects; only mounts a view when
  it has real derived data so the components' demo fallbacks never show).
- `components/chat/EvidenceCard.tsx`: added a "Pin to board" icon button
  (`useParams` for `caseId`/`sessionId`, `boardStore.pin`, `e.stopPropagation()`).
  Filled pin + disabled once `pinsByCase` shows a citation with that `fir_id`.
- **Orphaned by this phase, delete in Phase 6**: `components/dashboard/DashboardPanel.tsx`
  and the analytics charts it pulled (`stats.tsx`, `recent-conversations.tsx`,
  `conversation-volume-chart.tsx`, `channel-breakdown-chart.tsx`). Left in place
  to keep the diff contained. `HypothesisWorkspace.tsx` also now orphaned —
  Phase 5 retires it.
- **Deliberate deviation from the plan**: the plan said *move* the 4 analytics
  charts under `components/workspace/`. They are chat-analytics mockups (volume,
  channel-breakdown) with no persistent-case meaning, so purpose-built
  `CitationsTable`/`KeySuspectsList` were written instead and the old files left
  to be deleted in Phase 6.

**Gates:** `npx vite build` clean · `npx vitest run` 13/13 · new/touched files
tsc-clean (`tsconfig.app.json` total unchanged at 37 pre-existing) · `oxlint src/`
— new files clean, 25 pre-existing warnings in untouched files.

**Live-verified in Chrome** (Test Case Beta, real backend): workspace shows
"Nothing pinned" empty state → open session → run query → expand Retrieved
Evidence → click pin on two citation cards (icon fills) → Workspace now lists
2 Pinned Citations + derived Entity Relation Network (2 FIR nodes) → add a
hypothesis via the strip ("1 recorded", OPEN) → **full page reload**: both pins
and the hypothesis persist. Zero console errors.

**Commit:** `feat: Phase 4 — case workspace + board persistence`.

---

## Phase 4 — original goal (for reference)

### 4.1 Backend — extend `backend/api/routes/cases.py` (keep NoSQL key conventions)

- **Board card layout** — new mutable doc `case_board_layout:{case_id}` →
  `{ cards: BoardCard[], updated_at, updated_by }`, separate from the append-only
  pin log `case_board:{case_id}`.
  - `GET /api/cases/{case_id}/board/layout` → `{ cards: [] }` (empty if absent).
  - `PUT /api/cases/{case_id}/board/layout` `{ cards }` — full replace under
    `get_case_lock` + `_require_collaborator`. Caps: `len(cards) <= 200`,
    `text max_length=2000`, `len(connections) <= 50`, `color` regex, `kind` enum,
    float coords. 422 on violation.
- **Hypotheses re-keyed to case** — `case_id: Optional[str] = None` on
  `HypothesisRecord` (`shared/hypothesis_models.py`); `create_hypothesis` also
  writes a `hypotheses_by_case:{case_id}` index (same locked RMW as
  `hypotheses_by_fir`); add `list_hypotheses_by_case`
  (`shared/hypothesis_engine.py`). `backend/api/routes/hypothesis.py`:
  `HypothesisCreateRequest` gains optional `case_id`, existing 4 routes stay
  byte-compatible. New in `cases.py`: `GET /api/cases/{case_id}/hypotheses`,
  `POST /api/cases/{case_id}/hypotheses` (thin wrapper injecting `case_id`).
  With no specific FIR, pass `case_id` as the `fir_id` value.
- **`delete_case` cleanup** — add `nosql_delete` for `case_board_layout:{id}` and
  `hypotheses_by_case:{id}` to the existing `delete_tasks`.
- No new router file. **Mirror `shared/` changes into `functions/ps_1_cis_function/`
  per the README rule** (check: does the hypothesis engine/model live in the
  mirror? — `job_dispatch` did not need mirroring in Phase 2, verify per-file here).
- Restart the backend after edits (uvicorn runs WITHOUT `--reload`):
  `source .venv/bin/activate && python -m uvicorn backend.main:app --host 0.0.0.0 --port 8001`.
  `pytest` is NOT in the venv — backend suites can't run here; verify by import +
  live curl / browser.

### 4.2 Frontend — `pages/CaseWorkspacePage.tsx`

Currently `pages/CaseWorkspacePage.tsx` renders `DashboardPanel`. Rework so data
is persistent + per-case:
- Citations table + Key Suspects ← `GET /api/cases/:id/board` filtered by
  `content_type` (`'citation'`, `'suspect'`).
- `NetworkGraph` + `CrimeMap` ← v1 derived client-side from pinned citation
  `content`.
- Hypotheses summary strip ← `GET /api/cases/:id/hypotheses`.
- Move `stats.tsx`, `recent-conversations.tsx` (→ `CitationsTable`),
  `conversation-volume-chart.tsx`, `channel-breakdown-chart.tsx` under
  `components/workspace/`.
- "Pin to board" control on citation rows / suspects / graph nodes →
  `POST /api/cases/:id/board`.
- Introduce `stores/boardStore.ts` (pins + layout) — consumed fully in Phase 5.

**Exit criteria:** workspace shows real persisted case data; pinning round-trips
(pin a citation → reload → still there); `vite build` + `vitest` green; backend
imports clean + live-verified. Commit `feat: Phase 4 — case workspace + board
persistence`. Update this file, mark Phase 5 next, stop for /compact.

---

## Phase 5 — DONE

The freeform **paper corkboard** at `/cases/:caseId/board`, persistent per case.

### Spike outcome — hand-rolled, NOT React Flow

`@xyflow/react` was **not added**. A corkboard is freeform absolute-positioned
paper with an SVG yarn layer — not a node-graph needing a layout engine, handles
or connection validation. React Flow would have shipped ~40KB + its own CSS to
scope away, for features we don't use. Went with the plan's documented fallback:
a single CSS `transform: translate() scale()` on a `.corkboard-surface`, pointer
events on `window` during drag (no pointer capture, so `[data-no-drag]`
descendants keep their own clicks), a native non-passive `wheel` listener for
cursor-anchored zoom, and a hand-drawn `<svg>` yarn layer. Zero new deps.

### Backend

None — Phase 4 already shipped `GET`/`PUT /api/cases/:id/board/layout` and
`GET`/`POST /api/cases/:id/hypotheses`.

### Frontend — new files

- **`stores/boardStore.ts`** (extended): `setLayout`, `upsertCard`, `patchCard`,
  `removeCard`, `persistLayout(caseId, delayMs=800)` (module-scoped debounce
  timers, PUT without rollback — drags already applied locally), `applyHypothesis`
  (upsert one record after resolve). Plus exported **`deriveBoardCards(layout,
  hypotheses, pins)`** — the server layout doc is authoritative for *placed*
  cards; hypotheses / citation pins / suspect pins with no layout entry are
  materialized at a deterministic FNV-hash scatter position (`hyp:<id>`,
  `fir:<firId>`, `suspect:<id>`), and stop being synthesized once dragged (which
  writes them to the layout).
- **`hooks/useHypotheses.ts`** — wraps the four calls unchanged: list + create in
  `boardStore` (shared with the workspace strip), `check` / `resolve` local
  (transient `checkLogs` + `busyId` state here).
- **`components/board/`**:
  - `CorkboardCanvas.tsx` — owns `view {x,y,k}`, pan (drag empty cork), wheel
    zoom (clamped 0.4–2, cursor-anchored), toolbar zoom/fit/reset, auto-fit once
    after `loadingByCase[caseId]` flips false, link mode (`toggleLink` — click
    two cards to cord, click a corded pair to cut), `addNote`, `addCardForEntity`
    (from a hypothesis's dashed entity chip), yarn-edge derivation (explicit
    `card.connections` solid + implicit hypothesis→refId dashed), fresh-edge
    animation for ~700ms after a link is drawn.
  - `BoardCardFrame.tsx` — draggable pinned-paper wrapper; screen delta ÷ zoom;
    `[data-no-drag]` guard; renders `Pushpin` + children; `<3px` move = select.
  - `HypothesisNoteCard.tsx` — ruled index card, status ribbon
    (open/confirmed/refuted), statement, entity chips (● has card / dashed +add),
    inline Check / Confirm / Refute with a reason textarea; check log renders
    under the body.
  - `SuspectTile.tsx` (initials plate), `FirCard.tsx` (id + type + district +
    confidence), `FreeNoteCard.tsx` (double-click → textarea, blur commits, trash
    button), `Pushpin.tsx` (`--pin-color` custom prop), `YarnLayer.tsx` (quadratic
    bezier with downward sag; `stroke-dashoffset` draw animation gated on
    `prefers-reduced-motion`), `BoardToolbar.tsx`.
- **`styles/board.css`** (new, `@import`ed into `index.css` after `casefolder.css`)
  — every rule scoped under `.corkboard`: cork surface (speckle grain, wood
  border, inset shadow), pins, index-card rules, yarn, toolbar, `.board-page` /
  `.board-stage` wrappers.
- **`pages/CorkboardPage.tsx`** — rewritten: `loadCase` on mount, `deriveBoardCards`
  via `useMemo`, EmptyState until cards exist, else `<CorkboardCanvas>`.
- `stores/entityStore` reused — suspect / FIR card click opens the app-level
  `EntityDrawer`.

### Retired

- **Deleted** `components/dashboard/HypothesisWorkspace.tsx` (broken `str`
  pseudo-types, direct `sessionStorage`) and `components/dashboard/DashboardPanel.tsx`
  (its only importer). Both were already orphaned after Phase 4. Phase 4's handoff
  said DashboardPanel goes in Phase 6 — done early here since deleting
  HypothesisWorkspace broke its import.
- **Still orphaned, for Phase 6 deletion**: `components/stats.tsx`,
  `recent-conversations.tsx`, `conversation-volume-chart.tsx`,
  `channel-breakdown-chart.tsx` (+ `delta.tsx` if unused).

### Gates

`cd client`: `npx vite build` clean (309 modules), `npx vitest run` 13/13,
`npx tsc -p tsconfig.app.json` — **0 errors in any Phase 5 file** (repo-wide count
dropped 37 → 27, the two deleted dashboard files took 10 pre-existing errors with
them), `npx oxlint src/` — 24 findings, all pre-existing (was 25; one fewer after
the DashboardPanel delete), **0 in `components/board/` or the new store/hook**.

### Live-verified in Chrome (real backend, Test Case Beta `c_98e67a51`)

Board renders with cork surface + pushpins + 1 hypothesis card (OPEN ribbon) + 2
FIR cards (from Phase 4's pins). Pan / wheel-zoom / toolbar zoom / fit / reset all
work. **Dragged the hypothesis card → reload → position restored.** Link mode:
corded hypothesis ↔ FIR → red sagging yarn → **reload → yarn restored** (persisted
in `BoardCard.connections`). Clicked **Check** → `POST …/hypothesis/:id/check`
round-trip, log rendered inline under the statement. Zero console errors
throughout. Auto-fit now waits for the layout doc so cards land centred (earlier
it fit to synth scatter positions and never re-fit).

### Known follow-ups (not blocking)

- Check logs are session-transient (no server list endpoint to re-read them).
- No per-card resize handle (cards use fixed per-kind dimensions).
- `deriveBoardCards` scatter can still overlap for hash collisions on 3+ unplaced
  cards; harmless once dragged.

---

## Phase 5 — original goal (for reference)

The freeform **paper corkboard** at `/cases/:caseId/board`. Full detail in the
plan file §"Phase 5".

**Canvas tech — `@xyflow/react` (React Flow v12), spike first (~half the phase):**
cork `<Background>` + one `SuspectTile` node + one `YarnEdge` at zoom ≠ 1.
Fallback if the aesthetic fights the viewport: `dnd-kit` +
`react-zoom-pan-pinch` + hand-rolled SVG yarn. React Flow ships its own CSS —
`@import` it and scope every override under a `.corkboard` root so it can't bleed
into `.dossier-*` / `.message`.

**Backend is already done** (Phase 4): `GET`/`PUT /api/cases/:id/board/layout`
(the `case_board_layout` doc, `BoardCard[]`) and `GET`/`POST
/api/cases/:id/hypotheses` exist and are wrapped in `lib/api.ts` +
`stores/boardStore.ts` (`layoutByCase`, `putLayout`, `hypothesesByCase`,
`addHypothesis`). Phase 5 is frontend-only.

**Do:**
- `pages/CorkboardPage.tsx` — `boardStore.loadCase(caseId)` then `<ReactFlow>`
  with `nodeTypes` / `edgeTypes` + a cork `<Background>`.
- `stores/boardStore.ts` — extend with derived `edges`, `moveCard/addCard/
  updateCard/removeCard/linkCards`, and debounce `putLayout` (~800ms) on drag.
- `components/board/`: `HypothesisNoteCard` (index-card, status ribbon
  open/confirmed/refuted), `SuspectTile` (photo + `Pushpin`), `FirCard`,
  `FreeNoteCard`, `YarnEdge` (red bezier + sag + pushpin caps), `Pushpin`,
  `BoardToolbar` (add-card palette, zoom, fit).
- `hooks/useHypotheses.ts` — wraps the 4 existing hypothesis calls unchanged:
  list via `GET /api/cases/:id/hypotheses`; create via `POST
  /api/investigation/hypothesis` (now takes `case_id`) or the case wrapper;
  check `POST …/{id}/check` → render `HypothesisCheckLog` on the card; resolve
  `POST …/{id}/resolve` → flips the ribbon.
- Behaviour: every hypothesis materialises as a card `id = "hyp:" +
  hypothesis_id`; cards with no layout entry auto-place (grid scatter) then
  persist. For each `linked_entity_id`, draw a `YarnEdge` to a board card whose
  `refId` matches, else offer "＋ add card for <id>". `onNodeDragStop` →
  `moveCard` → debounced `persistLayout`.
- **Retire `components/dashboard/HypothesisWorkspace.tsx`** (flat list, broken
  `str` types, direct `sessionStorage` reads) — now orphaned since Phase 4.

**Exit criteria:** board persists (add card → drag → reload → position kept);
hypotheses editable there; `vite build` + `vitest` green; live-verified in
Chrome. Commit `feat: Phase 5 — corkboard hypothesis/evidence board`. Update this
file, mark Phase 6 next, stop for /compact.

---

## Phase 6 — NEXT. Goal

Theme refinement — keep the "Case File" identity, no visual redesign. Full detail
in the plan file §"Phase 6".

**Do:**
- **Token reconciliation** (`client/src/index.css`): `:root` defines two parallel
  sets with duplicated literals (`--bg-*`/`--accent-*`/`--text-*` vs shadcn
  `--background`/`--primary`/…); `.dark` is a verbatim copy (no-op). Make the
  custom primitives the single source of truth; shadcn tokens **reference** them
  (`--background: var(--bg-primary)`, `--primary: var(--accent-primary)`, charts →
  `--accent-*`/`--accent-gold`, …). Collapse or delete `.dark`. Keep `@theme
  inline`.
- **Contrast fix**: `--text-tertiary #8a7d67` on `--bg-primary #e9e1cd` ≈ 3.0:1 —
  fails ≥4.5:1 for body text. Darken to ~`#6f6047` or restrict to large /
  decorative labels; audit every usage.
- **`Login.tsx` tokenization**: ~40 inline hex / `fontFamily` literals + an
  `inkBorder()` helper → replace with tokens; move chrome into `styles/auth.css`
  (`.auth-screen`, `.auth-card`, `.auth-field`, classification bar, folded
  corner); `inkBorder()` → CSS `:focus-within` + `[aria-invalid]`. Same markup.
- **`index.css` reorg**: split into ordered `@import`ed partials under
  `client/src/styles/`: `tokens.css` → `base.css` → `theme-casefile.css` →
  `dashboard.css` (`.dossier-*`) → `entity-drawer.css` → `auth.css` (new) →
  `casefolder.css` → `sidebar.css` → `ui.css` → `board.css`. `index.css` keeps
  only font `@import`, tailwind/tw-animate/shadcn imports, the partials, `@theme
  inline`, `@layer base`.
- **Delete orphans**: `components/stats.tsx`, `recent-conversations.tsx`,
  `conversation-volume-chart.tsx`, `channel-breakdown-chart.tsx` (+ `delta.tsx`,
  `formater.ts` if grep-clean). `DashboardPanel.tsx` + `HypothesisWorkspace.tsx`
  already deleted in Phase 5.
- **Cosmetic debt noted earlier**: folder tiles read a little flat; chat greeting
  spacing; entity-drawer `border-left:3px` review.
- **Motion audit**: only two authored moments — folder open (Phase 1) + yarn
  draw (Phase 5). Everything else stays 120–280ms ease. Honor
  `prefers-reduced-motion`.
- **Audit**: `impeccable/scripts/detect.mjs` + `palette.mjs`; manual pass against
  `craft-floor.md` for required states (hover / disabled / loading / error /
  empty / focus / responsive) on every redesign component; 65–75ch prose measure.

**Exit criteria:** `vite build` + `vitest` green; tokens single-sourced;
`--text-tertiary` passes contrast; Login has no inline literals; orphans gone;
live-verified in Chrome. Commit `feat: Phase 6 — theme reconciliation`. Update
this file, mark Phase 7 next, stop for /compact.

---

## Phase 7 — verification (after Phase 6)

Playwright `tests/test_ui_redesign_playwright.py` (folder-grid landing, dialog
case create, session URL shape, query → progress → evidence, board drag →
reload persists, pin → reload persists, SSE poll-recovery). Backend
`tests/test_cases_board_layout.py` (PUT/GET layout, 201-card / oversized-text /
oversized-connections → 422, case-lock, `delete_case` cleanup) + hypothesis
`case_id` tests. Impeccable screenshot audit at 1440 / 768 / 375 for `/login`,
`/cases`, `/cases/:id`, `/cases/:id/sessions/:sid`, `/cases/:id/board`.
