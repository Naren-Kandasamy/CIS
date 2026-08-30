# CIS — Full change log: `main` → redesigned workspace

Everything that changed from the pre‑redesign `main` up to the current
deployment (`6a8fa60`, 2026‑08‑30). Reads top‑to‑bottom as a story; the last
two sections are a reference map.

Companion docs in this folder:
`PHASE_HANDOFF.md` (phase‑by‑phase build log), `SESSION_HANDOFF.md`
(pick‑up notes), `INDIC_ASR_INTEGRATION.md` (voice port map).

---

## TL;DR

The frontend went from a **single‑screen chat app** (`App.tsx`, one big
component, one live query at a time) to a **multi‑route investigation
workspace**:

> Log in → a room of manila **case folders** → open one → a per‑case
> **workspace** (pinned citations, key suspects, a real graph‑DB entity
> network, a map) with chat **sessions as files inside the case** and a
> freeform **corkboard** for hypotheses and evidence with red‑yarn links.
> A separate **global dashboard** holds cross‑case analytics.

On top of that: **Indic / code‑mixed voice input**, the **entity relation
network wired to the live Memgraph graph**, and a final round of workspace
fixes — **evidence now survives a page reload**, **pinning is reachable from
the chat**, graph nodes are clickable, hypotheses keep both a short gist and
the full text, and each case gets a district map.

All of it is on `main` and deployed to Catalyst.

---

## Timeline

| Milestone | Commit | What landed |
|---|---|---|
| Pre‑redesign baseline | `22b5666` | single‑screen `App.tsx` chat + a mock "dashboard panel" |
| Swagger lockdown | `33dd1df` | public FastAPI docs disabled |
| Catalyst token hardening | `1203739` | serialised token refresh + retry transient NoSQL 5xx |
| **UI redesign** (Phases 0–8) | **`6001c82`** (PR #24) | router, case folders, per‑case workspace, corkboard, real ER network, theme pass, global dashboard |
| **Indic ASR** | **`712aec6`** (PR #26) | browser + cloud voice input, code‑mixed normalizer |
| Drop dead ONNX path | `7828fd4` (PR #27) | removed the non‑functional in‑repo ONNX ASR; cloud cascade only |
| **Workspace fixes** | **`6a8fa60`** | evidence/visualization persistence, pinning wired, graph‑click fix, victim view, FIR labels, hypothesis gist/detail, district map |
| **Catalyst deploy** | — | all four targets live |

---

# Part I — The UI redesign (PR #24)

## Before

- One route. `client/src/App.tsx` (~800 lines) did auth, layout, the sidebar,
  the chat transcript, the SSE loop, the evidence panel and a mock analytics
  "DashboardPanel" with hardcoded charts.
- Chat sessions were client‑generated UUIDs with **no server‑side ownership
  check** (IDOR) and no concept of a "case".
- "Pinning", "hypotheses", "key suspects" existed as UI mockups with no
  persistence.
- The entity relation network rendered a hardcoded demo graph.

## After — architecture

**Routing** — `client/src/router.tsx`, `createBrowserRouter(…, {basename:'/app'})`.
`RequireAuth` guards everything under `AppShell`.

| Route | Page | What it is |
|---|---|---|
| `/login` | `LoginPage` | tokenized onto `styles/auth.css`; pure‑CSS focus / invalid states |
| `/cases` | `CasesIndexPage` | **the folder room** — manila `CaseFolder` tiles with an open animation; post‑login lands here |
| `/dashboard` | `GlobalDashboardPage` | **cross‑case** analytics, separate from any case |
| `/cases/:caseId` | `CaseWorkspacePage` | per‑case workspace (see below) |
| `/cases/:caseId/board` | `CorkboardPage` | the freeform corkboard |
| `/cases/:caseId/sessions/:sessionId` | `SessionChatPage` | a chat "file" inside the case |

**State** — zustand stores under `client/src/stores/`:
`authStore`, `casesStore`, `chatStore`, `boardStore`, `entityStore`.
`chatStore` owns `messagesBySession` and runs the SSE loop with
`getState().patchMessage(...)` (no stale closures — the old
`updateSessionMessages(prev => …)` captured a stale `targetSessionId`).

**API** — every call goes through typed wrappers in `client/src/lib/api.ts`
(`apiFetch<T>()` + `ApiError` carrying `.status`). The SSE query path stays in
`lib/sse.ts` (`streamQuery`), with `lib/pollJob.ts` recovering a job whose SSE
stream got cut by AppSail.

**CSS** — `client/src/index.css` is now font/framework imports + 10 ordered
partials under `client/src/styles/`
(`tokens.css` → `base.css` → `theme-casefile.css` → `dashboard.css` →
`entity-drawer.css` → `auth.css` → `casefolder.css` → `sidebar.css` →
`ui.css` → `board.css`). `tokens.css` is the single source of truth: custom
primitives (`--bg-*` / `--accent-*` / `--text-*`); shadcn tokens
`var()`‑reference them. Tailwind v4 CSS‑first, **no `tailwind.config.js`**, no
dark mode. The aged‑paper "Case File" look is kept and refined, not replaced.

## After — the phases (build log summary)

| Phase | What it did |
|---|---|
| **0 — Foundation** | `types/` module, `lib/sse.ts` + `lib/pollJob.ts` + `lib/api.ts` extracted from `App.tsx`, ~30 dead shadcn scaffold files deleted |
| **1 — Router + shell + folders** | routes, `authStore`/`casesStore`/`entityStore`, `AppShell` + `CaseDrawerSidebar`, the `CaseFolder` open animation, chat lifted out of `App.tsx` |
| **2 — Chat state store** | `messagesBySession` → `chatStore`; **`PATCH /api/sessions/:id {title}`** so the sidebar shows the first query as the session label; local‑dev `history:{sid}` write fix |
| **3 — Chat component split** | `SessionChatPage` 460 lines → ~40; UI now in `components/chat/*`; `hooks/useVoiceRecorder.ts`; **`App.tsx` deleted** |
| **4 — Workspace + persistence** | **`PUT/GET /api/cases/:id/board/layout`**, **`GET/POST /api/cases/:id/hypotheses`**, `hypotheses_by_case:{id}` index, `boardStore`, the per‑case workspace, "Pin to board" on evidence cards |
| **5 — Corkboard** | hand‑rolled pan/zoom board (no React Flow), draggable pinned cards, SVG **red‑yarn links**, inline hypothesis check/confirm/refute; retired the old `HypothesisWorkspace` + `DashboardPanel` |
| **6 — Theme refinement** | tokens single‑sourced, `index.css` split into partials, `Login.tsx` tokenized, `--text-tertiary` contrast fix (3.0:1 → 4.9:1), deleted 4 mock charts + the whole `components/ui/` shadcn scaffold, `prefers-reduced-motion` audit |
| **7 — Verification** | new backend tests (`test_cases_board_layout.py`, hypothesis `case_id`), Playwright script, **found + fixed** a middleware bug (a blanket 2 KB JSON‑body cap was silently 413‑ing corkboards > ~10 cards) |
| **8 — Global dashboard** | brought back cross‑case analytics at its own `/dashboard` route + sidebar link; Key Suspects + hypotheses stay per‑case only |

## Backend endpoints added (all in `backend/api/routes/`, not mirrored)

- `PATCH /api/sessions/:id` `{title}` — sidebar session labels
- `PUT` / `GET /api/cases/:id/board/layout` — corkboard card positions + cords
- `GET` / `POST /api/cases/:id/hypotheses` — case‑scoped hypotheses
- `GET /api/investigation/hypothesis/:id/check` — read back the last persisted check log
- `GET /api/cases/:id/graph` and `GET /api/graph` — entity relation network (Part III)

`shared/hypothesis_{models,engine}.py` gained `case_id` + a
`hypotheses_by_case:{id}` index (mirrored to `functions/`).
`input_validator.py` got a `/board/layout` exemption from the 2 KB body cap
(`MAX_BOARD_LAYOUT_BYTES = 256 KB`).

---

# Part II — Voice input: Indic / code‑mixed ASR (PRs #26, #27)

Ported from Hemnath D's `feat/indic-asr` onto the redesigned chat components
(his PR #25 couldn't merge — it edited the now‑deleted `App.tsx`).

**Three independent layers:**

1. **Browser live ASR** — `client/src/lib/indicSpeech.ts`
   (`IndicSpeechRecognizer`, Web Speech API). Live in‑browser transcription
   with interim results, Chrome/Edge. Fills the input box as you speak. This
   is the **primary** path.
2. **Cloud ASR fallback** — `client/src/lib/audioRecorder.ts`
   (`AudioRecorderVAD`, 16 kHz WAV + silence auto‑stop) →
   `POST /api/transcribe` → server cascade **HuggingFace → Groq/Whisper → Zia**
   (`shared/catalyst_client.py transcribe_audio`). Used when
   `SpeechRecognition` is unavailable. With no extra keys set it behaves
   exactly like before (Zia).
3. **Normalizer** — `INDIC_PHONETIC_PATTERNS` gazetteer (Bengaluru stations,
   IPC/BNS section forms, code‑mixed verbs ×7 languages) +
   `preprocess_indic_phonetics()` + `normalize_transcript_text()` (a
   Karnataka‑Police LLM prompt). Exposed as `POST /api/transcribe/normalize`.
   Best‑effort — returns the input unchanged on failure. Verified:
   `"koramangala station nalli Ramesh yaaru andu heli, section 379 cases torisi"`
   → `"Show details of Section 379 IPC cases for Ramesh at Koramangala station"`.

**`InputBar.tsx`** — 7‑language voice selector (EN / KN / HI / TA / TE / MR /
MIX), folded down to the pipeline's `en|hi|kn` for `/api/query`.
`hooks/useVoiceRecorder.ts` orchestrates both paths.

**PR #27** removed the bundled `models/indic_asr_tiny.onnx` +
`onnx_indic_asr.py` + `numpy`/`onnxruntime`: forensics showed the `.onnx` was
Whisper‑tiny's **encoder only** (no decoder), and its "transcription" was
`argmax` over hidden states through a 26‑word toy vocab — it returned
`"HSR Layout"` for silence, noise and real speech alike, and it *shadowed* the
working cloud cascade. Cloud cascade verified on real TTS speech.

**Env:** `HF_API_KEY`, `GROQ_API_KEY` in `backend/.env` (+ HF in
`pipeline_function/.env`). Without them the cascade still falls through to Zia.

---

# Part III — Entity relation network (wired to the graph DB)

Both ER networks used to render hardcoded demo elements. `backend/api/routes/graph.py`
now queries the **Memgraph investigation graph**.

- **`GET /api/cases/:id/graph`** — per‑case. Seed FIRs = that case's pinned
  citations + hypotheses + **FIR UUIDs scraped from the case's own session
  answers** (`history:{sid}`). One hop over
  `(:Accused)-[:ACCUSED_IN]->(:FIR)` and `(:Victim)-[:VICTIM_IN]->(:FIR)`;
  `FIR.district` becomes a Location node. Collaborator‑gated. Feeds
  `WorkspaceGraphs.tsx`.
- **`GET /api/graph`** — officer‑wide. Union of those seeds across every case
  in `user_cases:{username}`. An Accused linked to FIRs from ≥ 2 distinct
  cases gets `data.shared` + `data.caseCount` (gold ring in the UI).
  **Thin‑graph fallback**: < 3 accused nodes → the top‑6 most‑connected
  accused across the whole graph are appended, faded (`data.overview`). Feeds
  `GlobalDashboardPage.tsx`.
- Graph DB unreachable → `{elements: [], degraded: true}` at HTTP 200. The
  overview layer is best‑effort and never fatal.

Related pipeline fix (`d62deed`): the query pipeline's
`MATCH (p:Person)-[r]->(f:FIR)` matched **nothing** — the graph labels
offenders `:Accused`, not `:Person`. Now fixed.

**Graph schema in use:** `:Accused` (`[:ACCUSED_IN]`), `:Victim`
(`[:VICTIM_IN]`), `:Account` (`[:TRANSFERRED]`), `:Phone`
(`[:CALLED]` / `[:PINGED]`), `:Vehicle` (`[:DETECTED]`), `:CellTower`,
`:ANPRCamera`. `FIR` props: `id, date, crime_no, district, crime_type,
modus_operandi, narrative`.

---

# Part IV — Workspace fixes (`6a8fa60`, this session)

Everything below shipped in one commit and one Catalyst deploy.

## 1. Evidence + visualization now survive a reload

**Problem:** history turns were stored as `{q, a}` only. Reopening a session
restored the answer text but **not** the evidence cards, the graph or the map —
you had to re‑run the query.

**Fix:** the history writers now persist the full turn —
`{q, a, evidence, visualization}` (evidence capped at 40 items/turn so a
10‑turn history doc stays inside the NoSQL value‑size limit).

- `backend/job_dispatch.py` (`_local_pipeline_runner`, local/inline path)
- `pipeline_function/main.py` (Catalyst Signals path) + `functions/` mirror

The frontend already read `h.evidence` / `h.visualization` in
`chatStore.loadHistory` — only the writers were missing it. Verified end‑to‑end
against the live backend (`history turns=1 keys=['q','a','evidence','visualization']
evidence_len=10`).

> Only turns created **after** this deploy carry evidence. Older turns show
> answer text only.

## 2. Pinning is now reachable from the chat

**Problem:** the only thing that created a pin was the tiny 📌 icon on an
evidence card (`content_type: 'citation'`). **Nothing** created a
`content_type: 'suspect'` pin — the Key Suspects panel could only ever say
"No suspects pinned yet". The person entity drawer (which is where a "pin
suspect" action belongs) could only be opened from the workspace graph, never
from the chat.

**Fix:**

- **Evidence cards** now show an **"Accused" chip row** — click a chip → the
  person drawer opens → **"Pin to Key Suspects"** button (full‑width, gold,
  under the risk banner). `item.data.accused_ids` is populated for
  graph‑sourced evidence (`executor.py`).
- **Entity drawer** — `PersonDetail` gained **"Pin to Key Suspects"**,
  `FIRDetail` gained **"Pin FIR as citation"**; accused / co‑accused name
  chips are now clickable (FIR → accused → pin).
- The chat's `openEntity` prop type was widened from `{type: 'fir'}` to the
  full `SelectedEntity`.
- Pin buttons and the "Log this analysis as a hypothesis" trigger were
  enlarged and given real button styling — they were faint and easy to miss.

Pinned suspects show in the **Key Suspects** panel on the workspace page and
as cards on the corkboard.

## 3. Graph node clicks were silently dead — fixed

**Problem:** clicking a node in the Entity Relation Network only made it grow
and highlight (Cytoscape's built‑in select styling). No detail panel opened.

**Root cause:** `NetworkGraph` bound its `tap` handler in a `useEffect` keyed
on `[graphElements, onNodeClick, evidence]`. On mount `cyRef.current` was still
`null` (a ref write doesn't re‑run the effect), and for stable props it never
rebound.

**Fix:** bind the tap handler in the `cy` callback (the one place
`react-cytoscapejs` reliably hands over the live instance), reading latest
props via refs. Clicking any node now opens the inline detail panel.

## 4. Proper Victim entity view

Victim nodes were falling through to the FIR view (so a victim showed a
nonsensical "Pin FIR as citation"). `'victim'` is now a real `EntityType`
with its own `VictimDetail` panel (linked cases + accused, no pin button).

## 5. `FIR <crime_no>` labels instead of raw UUIDs

FIR records carry an 18‑digit `crime_no` but the UI was showing the internal
UUID (`a162ad7c-…`). Root cause: `crime_no` was missing from the evidence
metadata the pipeline builds. Added it (`executor.py` + `functions/` mirror);
a shared `firLabel()` helper (`client/src/lib/utils.ts`) now renders
`FIR <crime_no>` everywhere, falling back to a short uppercased 8‑char stub
only when there is genuinely no crime number. The drawer also hides the raw
UUID sub‑line.

## 6. Hypotheses keep a short gist **and** the full text

New optional **`detail`** field on `HypothesisRecord` (≤ 8000 chars) holds the
full source analysis verbatim; `statement` is the short, editable gist.

- **Logging from chat** (`HypothesisSuggestion.tsx`): seeds `statement` from a
  1–2 sentence summary of the analysis; stores the untouched analysis as
  `detail`.
- **Corkboard card** (`HypothesisNoteCard`): gist only, clamped to 6 lines —
  it's the glance view, no card can grow into a wall of text.
- **Workspace "Working Hypotheses" list** (`HypothesisStrip`): gist by
  default + **"▾ Read full hypothesis"** → expands to `detail` (or a long
  legacy statement). This is the full‑read surface.

Backend: `shared/hypothesis_models.py` (+ mirror), both create request models
and endpoints (`cases.py`, `hypothesis.py`).

## 7. District‑centroid case map

The per‑case `<CrimeMap>` only drew markers when a citation carried
`lat`/`lng` — and FIR records only have a `district` string, so it never
appeared. New `client/src/lib/districts.ts` maps the 6 Karnataka districts in
the corpus (with transliteration aliases: Bangalore→Bengaluru,
Gulbarga→Kalaburagi, …) to HQ centroids. `WorkspaceGraphs.deriveMarkers` now
groups district‑only FIRs onto their centroid — one marker per district with a
count + crime numbers. `CrimeMap` zooms in for a single‑district case, pulls
back to all‑Karnataka for multi‑district.

## 8. Misc

- Corkboard page header: an **"EVIDENCE BOARD"** eyebrow above the case title
  (it was showing only the case name).
- `shared/` ↔ `functions/` `catalyst_client.py` mirror resynced
  (`transcribe_and_normalize` had drifted).

---

# How everything works now — the full journey

### 1. Log in

`dysp1` / `demo1234` → lands on **`/cases`**.

### 2. The folder room (`/cases`)

Manila `CaseFolder` tiles + a dashed "＋ New case" folder. Cases are **per
user**: `GET /api/cases` returns only cases where your username is in that
case's `collaborators` array (indexed by `user_cases:{username}`). A new case
is an empty container — title, crime_no, district.

> There is **no collaboration UI** yet — the backend has an add‑collaborator
> endpoint but nothing calls it. Multi‑user cases today are seeded by script.

### 3. Inside a case (`/cases/:caseId`)

The **workspace** page:

- **Working Hypotheses** — list + quick‑add; each shows the gist, with
  "Read full hypothesis" when there's more.
- **Citations** — FIRs pinned to this case.
- **Key Suspects** — persons pinned to this case.
- **Entity Relation Network** — `GET /api/cases/:id/graph`. Fills in from FIRs
  the case has *touched*: pinned citations, hypotheses, or FIR UUIDs cited in
  this case's chat answers. Click a node → inline detail panel → pin.
- **Geospatial Distribution** — district‑centroid markers from pinned
  citations.

### 4. A chat session (`/cases/:caseId/sessions/:sessionId`)

Sessions are server‑issued `s_…` ids, ACL‑inherited from the parent case.
Ask a question (typed or voice) → `POST /api/query` → SSE stream:
7‑step pipeline stepper → streamed answer → **evidence cards**.

On each evidence card:

- the **📌 Pin** pill pins the FIR as a **citation**;
- the **Accused chips** open the person drawer → **Pin to Key Suspects**;
- **"Log this analysis as a hypothesis"** captures the answer's Analytical
  Synthesis (gist + full `detail`) into the case.

The turn (question, answer, evidence, visualization) is written to
`history:{sessionId}`. **Reopen the session later and it all comes back** —
cards, graph, map.

### 5. The corkboard (`/cases/:caseId/board`)

Every hypothesis, pinned citation and pinned suspect materializes as a
draggable pinned‑paper card. Drag to place (positions persist via
`case_board_layout:{id}`), link‑mode to draw **red yarn** between cards, add
free notes. Hypothesis cards have inline **Check / Confirm / Refute**.

### 6. The global dashboard (`/dashboard`)

Cross‑case analytics, separate from any case: stat cards, crime trend +
distribution charts, recent citations, the **officer‑wide** entity relation
network (`GET /api/graph`, gold ring on accused spanning ≥ 2 cases), and a
Karnataka map. Most panels render from synthetic fallback data; the ER network
is live.

---

# Data model reference

### Two separate stores

| | Intelligence corpus | Case workspaces |
|---|---|---|
| **Where** | Memgraph graph + Zoho KB + ZTSQL `cases` table | Catalyst NoSQL (`case:{id}`, indexed by `user_cases:{username}`) |
| **What** | ~8,000 FIRs, ~40k financial transfers, CDR, ANPR — the haystack | investigation folders a user creates |
| **Scope** | global, unowned; reached only *through a query* | per user via `collaborators` |

### NoSQL keys (Catalyst `AppKeyValueStore`)

| Key | Holds |
|---|---|
| `user:{username}` | credentials + role + display name |
| `user_cases:{username}` | `[case_id, …]` for that officer |
| `case:{case_id}` | title, crime_no, district, status, `collaborators`, timestamps |
| `case_sessions:{case_id}` | `[session_id, …]` |
| `session_meta:{session_id}` | session id, case id, created_by, title, last_activity |
| `history:{session_id}` | `[{q, a, evidence, visualization}, …]` — last 10 turns |
| `session:{session_id}` | coreference state for follow‑ups (`prior_query`, `prior_evidence_items`) |
| `job:{job_id}` | pipeline job status (SSE poller reads this) |
| `case_board:{case_id}` | append‑only pin log — `{pinned_by, pinned_at, content_type, content}` |
| `case_board_layout:{case_id}` | mutable card positions + cords |
| `hypothesis:{id}` | one `HypothesisRecord` |
| `hypotheses_by_fir:{fir_id}` / `hypotheses_by_case:{case_id}` | id indexes |
| `last_check:{hypothesis_id}` | last hypothesis check log |
| `cache:ner_intent:{hash}` | NER cache (1 h TTL) |

### `HypothesisRecord`

```
hypothesis_id, fir_id, case_id?, officer_id,
statement,           # short gist, officer-authored
detail?,             # full source text, revealed by "Read full hypothesis"
linked_entity_ids[], status (open|confirmed|refuted), created_date,
resolved_by?, resolved_reason?, resolved_date?
```

### Pin `content_type`

- `citation` — a FIR: `{fir_id, crime_no, confidence, crime_type, data}`
- `suspect` — a person: `{id, label, role, data}`
- (`fir` / `note` also understood by the board renderer)

---

# Key files map

### Frontend (`client/src/`)

| Area | Files |
|---|---|
| Routing / shell | `router.tsx`, `layouts/AppShell.tsx`, `components/nav/CaseDrawerSidebar.tsx` |
| Pages | `pages/{LoginPage,CasesIndexPage,GlobalDashboardPage,CaseWorkspacePage,CorkboardPage,SessionChatPage}.tsx` |
| Stores | `stores/{auth,cases,chat,board,entity}Store.ts` |
| API / SSE | `lib/api.ts`, `lib/sse.ts`, `lib/pollJob.ts` |
| Chat | `components/chat/*` — `ChatView`, `MessageList`, `MessageBubble`, `EvidencePanel`, `EvidenceCard`, `HypothesisSuggestion`, `InputBar`, `PipelineProgress`, `VoiceVisualizer` |
| Workspace | `components/workspace/*` — `HypothesisStrip`, `CitationsTable`, `KeySuspectsList`, `WorkspaceGraphs` |
| Corkboard | `components/board/*` — `CorkboardCanvas`, `BoardCardFrame`, `HypothesisNoteCard`, `SuspectTile`, `FirCard`, `FreeNoteCard`, `YarnLayer`, `Pushpin` |
| Entity drawer / graph | `components/dashboard/{EntityDrawer,NetworkGraph,CrimeMap}.tsx` |
| Voice | `lib/indicSpeech.ts`, `lib/audioRecorder.ts`, `hooks/useVoiceRecorder.ts` |
| Helpers | `lib/analysis.ts` (`extractAnalysis`, `summarizeAnalysis`), `lib/utils.ts` (`firLabel`, `fetchWithRetry`), `lib/districts.ts` |
| CSS | `index.css` + `styles/*.css` (10 partials) |

### Backend

| Area | Files |
|---|---|
| Routes | `backend/api/routes/{query,cases,sessions,hypothesis,graph,transcribe,translate,feedback,exclusions,health,export,tts,ocr,auth,review_queue}.py` |
| Middleware | `backend/api/middleware/{input_validator,rbac}.py` |
| Pipeline dispatch | `backend/job_dispatch.py`, `backend/sse_poller.py` |
| Pipeline (Signals) | `pipeline_function/main.py`, `pipeline_function/pipeline/**` (langgraph router, retrieval executor, synthesizer, …) |
| Shared (mirrored to `functions/ps_1_cis_function/shared/`) | `shared/{catalyst_client,graph_client,hypothesis_models,hypothesis_engine,models,auth,…}.py` |

**Mirror rule:** `shared/` edits must be copied into
`functions/ps_1_cis_function/shared/`. `backend/api/routes/*` and middleware
are **not** mirrored (AppSail deploys `backend/` directly).

---

# Deployment state

`main` @ `6a8fa60`, deployed to Catalyst project **PS1‑CIS** (Development):

| Target | Kind |
|---|---|
| `ps_1_cis_function` | Signals event function (the pipeline) |
| `job_test_func` | job function |
| `ps1-cis-client` | web client (`client/dist`) |
| `backend` | AppSail (FastAPI) |

- **App:** `https://ps1-cis-60075634347.development.catalystserverless.in/app/index.html`
- **Backend:** `https://backend-50043491738.development.catalystappsail.in`

### Verification at deploy

- Backend: `126 passed` (`pytest`)
- Frontend: `23 passed` (vitest), `tsc` clean, production build clean

### Known open items

- **Collaboration UI** — add/remove collaborator has a backend endpoint (add
  only) but no frontend; cross‑user cases are script‑seeded.
- **Legacy history turns** — turns from before the `6a8fa60` deploy have no
  stored evidence; they show answer text only.
- **Voice HF hop** — HuggingFace was DNS‑blocked in the dev sandbox (Groq +
  Zia verified). Confirm from the real network; rotate the pasted `HF_API_KEY`.
- **Dashboard analytics panels** (stat cards, trend/donut charts, recent
  citations, map default markers) render from synthetic fallback data, not
  live aggregates — by design, matching the reference screenshots.
- **No responsive layout** — desktop workstation tool by design (fixed 280 px
  sidebar, `max-width:1600px` shell).
