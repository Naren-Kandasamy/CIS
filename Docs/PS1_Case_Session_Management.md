# PS-1: Case & Session Management Layer
## New Capability — Persistent, Multi-Officer Case History (Replacing Anonymous Per-Refresh Sessions)

**Status:** New addendum to Architecture v8 / Implementation v8.
**Scope:** This adds a **Case** as a first-class object above Session. Today, `session_id` is a random client-generated UUID with no owner, no title, no link to any real investigation, and no way to list or reopen it after a refresh. This doc introduces Cases (persistent, shareable, ownable) containing Sessions (individual chat threads), and the exact concurrency rules for when more than one officer touches the same case.
**Written for:** direct hand-off to Antigravity as an implementation task — every section states current state, target state, and the exact files to touch, matching the convention of `PS1_Evidence_Language_Detection.md`.

---

## 1. Context — Why This Is Two Concepts, Not One

The originating question was: *"multiple people might work on one case, or different people work on different cases — how do we handle that?"* That question only has a clean answer if we stop treating "session" as the unit of ownership, because a session and a case have genuinely different lifetimes and different sharing rules:

- A **Session** is one continuous line of query → evidence → answer, run by **one officer, alone**, in one sitting. It's a scratchpad. Two officers should never be editing the same session at the same time — that's a shared-document-editing problem (real-time merge conflicts, cursors, presence) that this system has no need to solve.
- A **Case** is the actual investigation — potentially spanning days, potentially touched by several officers of different ranks, each running their *own* sessions against it. The case is the shared, persistent thing. The sessions underneath it are personal and independent.

**The design decision this doc makes:** multiple officers on one case means multiple *sessions* under a shared *case*, not multiple people editing one session. This sidesteps real-time collaborative-editing complexity entirely — each officer's line of questioning stays their own, but everyone attached to the case can see every session that's happened under it, in a read-only capacity, the same way multiple detectives can each read every report in a shared case file without simultaneously writing in the same notebook.

This mirrors the same principle already used elsewhere in this project (see `PS1_Evidence_Language_Detection.md` Section 3): prefer a deterministic, simple mechanism over a more powerful but riskier one, when the simple mechanism covers the actual requirement.

---

## 2. Current State vs Target State

| Aspect | Current (Implementation v8) | Target (this doc) |
|---|---|---|
| Session identity | Client generates a random UUID v4 in `sessionStorage` on page load (`client/src/App.tsx` line ~19). Server never assigns or validates ownership of it. | Server assigns `session_id` when a session is created via a new endpoint, tied to the authenticated user and a `case_id`. |
| Session persistence | `history:{session_id}` already exists in Catalyst NoSQL (`backend/job_dispatch.py`), capped at last 10 exchanges. Data survives, but nothing can list or find it again. | Same `history:{session_id}` storage, unchanged — now discoverable via case → session indexes. |
| Case concept | Does not exist. A "case" in the UI sense is really just whatever the LLM happens to retrieve for a given query — there's no persistent object an officer opens, names, or returns to. | `case:{case_id}` object: title, optional link to a real FIR/crime number, owner, collaborators, status, timestamps. |
| Multi-officer access | Not handled at all — there is no mechanism by which a second officer could even know a given session exists. | A case has one owner (creator) and a collaborators list. Any officer on that list can see all sessions under the case (read-only for others' sessions) and can start their own new session under it. |
| Access control | `/api/query` takes a bare `session_id`, validates only that it's a syntactically valid UUID4 (`backend/api/routes/query.py`) — no ownership or access check at all. | `/api/query` (and new case/session endpoints) validate that the authenticated user (from the existing Bearer-token RBAC middleware) is either the case owner or a listed collaborator before allowing access. |
| Concurrency | `get_session_lock(session_id)` already exists and is used narrowly around the history read-modify-write in `_local_pipeline_runner` (`backend/job_dispatch.py`) — this already correctly handles two *sessions* running concurrently without corrupting each other's history. | Reused as-is for session-level history writes (no change needed there — it already does the right thing). A new, separate `get_case_lock(case_id)` guards case-level metadata writes (adding a collaborator, renaming, closing the case), which is a different critical section than session history. |
| Frontend | Single hardcoded chat thread, `SESSION_ID` fixed for the page's lifetime, no sidebar list, no way to switch. | Case-folder sidebar: list of cases the user has access to → expand to see sessions under each case (own + collaborators') → click to reopen a session's history, or start a new session under an existing case. |

**The one-sentence version:** a `case` is a shared, persistent, multi-officer container; a `session` inside it stays single-officer and reuses the locking pattern that already exists — nothing about how session history itself is written needs to change, only how sessions get *discovered, grouped, and access-controlled*.

---

## 3. Design Principles

1. **Sessions are never co-edited.** No two officers write into the same session concurrently. If this constraint is ever violated by a future feature (e.g. "let two officers share one live chat"), that is a materially different, much harder problem (real-time sync) and should be a separate design doc, not folded into this one.
2. **A case has exactly one owner, and an explicit collaborator list — no implicit or automatic sharing.** An officer only sees a case if they created it or were explicitly added. This matches how `PS1_Evidence_Language_Detection.md` Section 3 principle 2 treats ambiguity: no implicit judgment calls, an explicit rule.
3. **Rank does not automatically grant case access.** A DySP does not automatically see every constable's case just by outranking them — the existing `ROLE_HIERARCHY` in `shared/auth.py` governs *route-level* permissions (e.g. who can export a PDF), not case visibility. Case visibility is purely the owner+collaborators list. (This is a deliberate, discussable choice — see Section 8, Open Question 1, if the team wants rank-based visibility instead or in addition.)
4. **Reuse the existing lock primitive; don't invent a second locking system.** `get_session_lock` already exists and already works correctly for the session-history race condition (see the `RC-02 FIX` comment already in `job_dispatch.py`, which narrowed the lock's scope for exactly this reason). Case-level metadata gets its own lock key, same underlying mechanism, not a new subsystem.
5. **Additive only.** No existing NoSQL key pattern (`user:`, `session:`, `history:`, `job:`, `cache:`) is renamed or restructured. New key prefixes (`case:`, `case_sessions:`, `user_cases:`) sit alongside them.
6. **The server assigns `session_id`, not the client.** This is a necessary behavior change, not just an addition — today `client/src/App.tsx` generates its own UUID with no server involvement at all, which is exactly why there's no ownership record right now. Session creation becomes a real POST call.

---

## 4. Data Model — New NoSQL Key Patterns

All stored in the same Catalyst NoSQL `AppKeyValueStore` table already used for `user:`, `session:`, `history:`, `job:` (see `shared/auth.py`'s own comment: *"avoids needing a second NoSQL table created in the console"* — same reasoning applies here, one table, prefix-namespaced).

### 4.1 `case:{case_id}`

```json
{
  "case_id": "c_8f3a1b2c",
  "title": "Robbery — MG Road, 14 Nov",
  "crime_no": "112/2023",
  "district": "Belagavi",
  "status": "open",
  "created_by": "dysp1",
  "created_at": 1783878000.0,
  "collaborators": ["dysp1", "si1"],
  "last_activity_at": 1783879000.0
}
```

- `case_id` — short random ID (not a full UUID — this appears in URLs/UI, keep it readable; `secrets.token_hex(4)` prefixed with `c_` is enough entropy for this scale).
- `crime_no` / `district` — optional, free text, lets an officer tie the case board entry to a real FIR number if one exists yet. Nullable — a case can start as an open-ended inquiry before a crime number is assigned.
- `collaborators` — always includes `created_by` (added automatically at creation, not a separate check every time).
- `status` — `"open"` or `"closed"`. Closed cases still visible, just visually deprioritized in the sidebar (not deleted — evidentiary trail, never delete).

### 4.2 `case_sessions:{case_id}`

```json
["s_1a2b3c", "s_4d5e6f"]
```

Simple list of session IDs under this case. Read once when a case is expanded in the sidebar; each session's own metadata is fetched separately (Section 4.3) rather than duplicated here, to avoid a second place that can drift out of sync with session data.

### 4.3 `session_meta:{session_id}`

```json
{
  "session_id": "s_1a2b3c",
  "case_id": "c_8f3a1b2c",
  "created_by": "dysp1",
  "created_at": 1783878000.0,
  "title": "cases linked to accused Ramesh K",
  "last_activity_at": 1783878900.0
}
```

- `title` — auto-derived from the first query in the session (truncated to ~60 chars), so the sidebar shows something meaningful ("cases linked to accused Ramesh K...") instead of a bare timestamp. Set once, at session creation, never rewritten — matches the existing convention of `history:{session_id}` being append-only/capped, not edited.
- This is new — `history:{session_id}` already exists and is unchanged; `session_meta` is the new discoverability layer sitting next to it.

### 4.4 `user_cases:{username}`

```json
["c_8f3a1b2c", "c_9d2e4f1a"]
```

Index for "which cases does this user have access to" — this is the single query the sidebar needs on load. Kept as a separate index (rather than scanning every `case:*` key, which the NoSQL client has no primitive for anyway — recall `PS1_Evidence_Language_Detection.md` Section 2's table already noted the mock/real NoSQL layer only supports exact-key fetch, no scan) — updated in two places: when a user creates a case, and when they're added as a collaborator (Section 5.3).

**Why a separate index instead of just reading `collaborators` off every case:** there's no way to enumerate "every case" cheaply (no scan primitive, per `shared/catalyst_client.py`'s `nosql_get`/`nosql_set` being exact-key only). `user_cases:{username}` is the answer to "what should I be able to list," populated at write time rather than computed at read time.

---

## 5. New Endpoints

All new routes go through the existing `RBACMiddleware` (`backend/api/middleware/rbac.py`) unchanged — they just need a valid Bearer session token, same as every other route today. No changes needed to the middleware itself; the case-ownership check is a second, separate check inside each route handler, layered on top of (not replacing) the existing "is this a valid session token at all" check.

### 5.1 `POST /api/cases` — Create a case

```python
# backend/api/routes/cases.py  (new file)

from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, Field
import secrets, time, json

from shared.catalyst_client import nosql_get, nosql_set, get_case_lock  # get_case_lock: new, see 5.4

router = APIRouter()

class CreateCaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    crime_no: str | None = Field(None, max_length=40)
    district: str | None = Field(None, max_length=60)

@router.post("/api/cases")
async def create_case(body: CreateCaseRequest, request: Request):
    username = request.state.username  # set by RBACMiddleware -- [VERIFY] exact attribute name, see 5.5
    case_id = f"c_{secrets.token_hex(4)}"
    now = time.time()

    case = {
        "case_id": case_id,
        "title": body.title,
        "crime_no": body.crime_no,
        "district": body.district,
        "status": "open",
        "created_by": username,
        "created_at": now,
        "collaborators": [username],
        "last_activity_at": now,
    }
    await nosql_set(f"case:{case_id}", json.dumps(case))
    await nosql_set(f"case_sessions:{case_id}", json.dumps([]))

    user_cases_doc = await nosql_get(f"user_cases:{username}")
    user_cases = json.loads(user_cases_doc["value"]) if user_cases_doc else []
    user_cases.append(case_id)
    await nosql_set(f"user_cases:{username}", json.dumps(user_cases))

    return case
```

### 5.2 `GET /api/cases` — List cases visible to the current user

```python
@router.get("/api/cases")
async def list_cases(request: Request):
    username = request.state.username
    user_cases_doc = await nosql_get(f"user_cases:{username}")
    case_ids = json.loads(user_cases_doc["value"]) if user_cases_doc else []

    cases = []
    for cid in case_ids:
        doc = await nosql_get(f"case:{cid}")
        if doc:
            cases.append(json.loads(doc["value"]))
    cases.sort(key=lambda c: c["last_activity_at"], reverse=True)
    return {"cases": cases}
```

`[VERIFY]` This does one `nosql_get` per case (N+1 pattern) — acceptable at hackathon/demo scale (an officer realistically has single-digit-to-low-double-digit cases open at once), but flag as a known scaling limit, not a silent one, if this doc is read post-hackathon.

### 5.3 `POST /api/cases/{case_id}/collaborators` — Add an officer to a case

```python
class AddCollaboratorRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)

@router.post("/api/cases/{case_id}/collaborators")
async def add_collaborator(case_id: str, body: AddCollaboratorRequest, request: Request):
    requester = request.state.username
    async with get_case_lock(case_id):
        doc = await nosql_get(f"case:{case_id}")
        if not doc:
            raise HTTPException(404, "Case not found")
        case = json.loads(doc["value"])

        if requester not in case["collaborators"]:
            raise HTTPException(403, "Only existing collaborators can add others")
        # NOTE: this is deliberately "any collaborator can add another," not
        # "only the owner can." Rationale: a case is a shared investigation,
        # not a personally-owned document -- restricting invites to only the
        # original creator would block a legitimate case handoff scenario
        # (e.g. the creating officer goes off-shift and a colleague needs to
        # loop in the next investigator). [VERIFY] confirm this matches how
        # KSP case-handling actually works day-to-day before treating this
        # as final -- it's a policy assumption, not a technical one.

        if body.username not in case["collaborators"]:
            case["collaborators"].append(body.username)
            await nosql_set(f"case:{case_id}", json.dumps(case))

            target_cases_doc = await nosql_get(f"user_cases:{body.username}")
            target_cases = json.loads(target_cases_doc["value"]) if target_cases_doc else []
            if case_id not in target_cases:
                target_cases.append(case_id)
                await nosql_set(f"user_cases:{body.username}", json.dumps(target_cases))

    return case
```

`[VERIFY]` Should there be a check that `body.username` is a real, existing user (i.e. call `get_user()` from `shared/auth.py` first)? As written, this would silently add a typo'd username to the collaborators list with no error. Recommend adding that check before this ships — flagged here rather than silently fixed, since it's a one-line addition but changes error-handling behavior worth a deliberate decision, not an assumption.

### 5.4 New shared primitive — `get_case_lock` in `shared/catalyst_client.py`

```python
# Addition to shared/catalyst_client.py, alongside the existing get_session_lock

_case_locks: dict[str, asyncio.Lock] = {}

def get_case_lock(case_id: str) -> asyncio.Lock:
    """
    Mirrors get_session_lock's pattern exactly, just keyed by case_id instead
    of session_id. Guards case-metadata read-modify-write (collaborator adds,
    status changes) -- a genuinely separate critical section from session
    history writes, so this is a distinct lock dict, not a shared one. Two
    officers adding different collaborators to two different cases at the
    same time should never block on each other.
    """
    if case_id not in _case_locks:
        _case_locks[case_id] = asyncio.Lock()
    return _case_locks[case_id]
```

`[VERIFY]` Confirm the exact current implementation of `get_session_lock` in `shared/catalyst_client.py` before adding this — the snippet above assumes a simple per-key `asyncio.Lock()` dict, matching what `backend/job_dispatch.py`'s usage implies, but the real implementation should be read directly (it wasn't fully reproduced in the files reviewed for this doc) to make sure `get_case_lock` actually mirrors it, including any cross-process caveats already noted elsewhere in this codebase (AppSail vs pipeline Function running as separate processes — an in-memory `asyncio.Lock` only guards within one process; `[VERIFY]` whether that's already a known accepted limitation for `get_session_lock` too, in which case `get_case_lock` inherits the same limitation consistently rather than introducing a new one).

### 5.5 `[VERIFY]` — How `request.state.username` actually gets set

Section 5.1–5.3 above assume the RBAC middleware attaches the authenticated username somewhere accessible to route handlers (`request.state.username`). Looking at `backend/api/middleware/rbac.py`, the middleware currently validates the Bearer token against `get_session()` and enforces rank — but the exact mechanism by which a downstream route handler *reads* the resulting username needs to be confirmed against the full file (not fully shown in the excerpt reviewed for this doc). If it's not currently exposed to route handlers at all, that's a small addition to the middleware (attaching the resolved session dict to `scope["state"]` or equivalent) needed before any of Section 5's routes can work — flagged explicitly so this isn't assumed to already exist.

### 5.6 `POST /api/cases/{case_id}/sessions` — Start a new session under a case

```python
class CreateSessionRequest(BaseModel):
    pass  # no body needed -- case_id is in the path, user comes from auth

@router.post("/api/cases/{case_id}/sessions")
async def create_session(case_id: str, request: Request):
    username = request.state.username
    doc = await nosql_get(f"case:{case_id}")
    if not doc:
        raise HTTPException(404, "Case not found")
    case = json.loads(doc["value"])
    if username not in case["collaborators"]:
        raise HTTPException(403, "Not a collaborator on this case")

    session_id = f"s_{secrets.token_hex(4)}"
    now = time.time()
    meta = {
        "session_id": session_id,
        "case_id": case_id,
        "created_by": username,
        "created_at": now,
        "title": None,  # set on first query -- see 5.8
        "last_activity_at": now,
    }
    await nosql_set(f"session_meta:{session_id}", json.dumps(meta))

    async with get_case_lock(case_id):
        sessions_doc = await nosql_get(f"case_sessions:{case_id}")
        sessions = json.loads(sessions_doc["value"]) if sessions_doc else []
        sessions.append(session_id)
        await nosql_set(f"case_sessions:{case_id}", json.dumps(sessions))

    return meta
```

### 5.7 `GET /api/cases/{case_id}/sessions` — List sessions under a case (own + collaborators')

```python
@router.get("/api/cases/{case_id}/sessions")
async def list_case_sessions(case_id: str, request: Request):
    username = request.state.username
    doc = await nosql_get(f"case:{case_id}")
    if not doc:
        raise HTTPException(404, "Case not found")
    case = json.loads(doc["value"])
    if username not in case["collaborators"]:
        raise HTTPException(403, "Not a collaborator on this case")

    sessions_doc = await nosql_get(f"case_sessions:{case_id}")
    session_ids = json.loads(sessions_doc["value"]) if sessions_doc else []

    sessions = []
    for sid in session_ids:
        meta_doc = await nosql_get(f"session_meta:{sid}")
        if meta_doc:
            sessions.append(json.loads(meta_doc["value"]))
    sessions.sort(key=lambda s: s["last_activity_at"], reverse=True)
    return {"sessions": sessions}
```

### 5.8 `GET /api/sessions/{session_id}` — Reopen a session's full history

```python
@router.get("/api/sessions/{session_id}")
async def get_session_history(session_id: str, request: Request):
    username = request.state.username
    meta_doc = await nosql_get(f"session_meta:{session_id}")
    if not meta_doc:
        raise HTTPException(404, "Session not found")
    meta = json.loads(meta_doc["value"])

    case_doc = await nosql_get(f"case:{meta['case_id']}")
    case = json.loads(case_doc["value"]) if case_doc else None
    if not case or username not in case["collaborators"]:
        raise HTTPException(403, "Not authorized for this session's case")

    history_doc = await nosql_get(f"history:{session_id}")
    history = json.loads(history_doc["value"]) if history_doc else []
    return {"meta": meta, "history": history}
```

Note the access check goes through the **case's** collaborator list, not anything stored on the session itself — a session has no independent ACL, it inherits access entirely from its parent case. This is intentional (Section 3, principle 2 extended: one source of truth for "who can see this," not two lists that could drift apart).

### 5.9 Modify `POST /api/query` — Require case context, set session title on first query

Current `backend/api/routes/query.py` accepts a bare `session_id` with no case linkage or ownership check at all. Minimal addition, not a rewrite:

```python
# backend/api/routes/query.py -- add after the existing QueryRequest validation,
# before dispatch_query_job() is called:

async def _authorize_and_stamp_session(session_id: str, username: str, query_text: str):
    meta_doc = await nosql_get(f"session_meta:{session_id}")
    if not meta_doc:
        raise HTTPException(404, "Session not found -- create one via POST /api/cases/{case_id}/sessions first")
    meta = json.loads(meta_doc["value"])

    case_doc = await nosql_get(f"case:{meta['case_id']}")
    case = json.loads(case_doc["value"]) if case_doc else None
    if not case or username not in case["collaborators"]:
        raise HTTPException(403, "Not authorized for this session")

    if meta["title"] is None:
        meta["title"] = query_text[:60]
    meta["last_activity_at"] = time.time()
    await nosql_set(f"session_meta:{session_id}", json.dumps(meta))

    case["last_activity_at"] = meta["last_activity_at"]
    await nosql_set(f"case:{meta['case_id']}", json.dumps(case))
```

`[VERIFY]` This adds two extra `nosql_get`/`nosql_set` round-trips to the hot path of every single query. Given the existing pipeline already has documented latency concerns (Signals stall risk, per `job_dispatch.py`'s own fallback-path comments), confirm this overhead is acceptable, or consider making the "stamp session/case activity" write fire-and-forget (`asyncio.create_task`, not awaited inline) rather than blocking the query response on it — flagged as a genuine tradeoff, not resolved in this doc, since it depends on how tight the existing latency budget actually is.

---

## 6. Frontend Changes

### 6.1 Remove client-generated `SESSION_ID`

`client/src/App.tsx` currently does:
```ts
const SESSION_ID = sessionStorage.getItem("ps1_session_id") ?? (() => { ... })();
```

This entire pattern goes away. `session_id` is no longer decided by the client at all — it comes back from `POST /api/cases/{case_id}/sessions` when a session starts, and gets held in component state (or still cached in `sessionStorage` for the *current* tab's convenience, but now as a value the server issued, not one the client invented).

### 6.2 New sidebar section — Case list

Sits above the existing Query/Dashboard nav buttons in the sidebar (`client/src/App.tsx`'s existing `<aside className="sidebar">` block). Styled per the existing folder-tab/punch-hole spine treatment already in `index.css` — each case as a tab, sessions nested underneath when expanded, matching the visual language already established (dashed rules, `IBM Plex Mono` for metadata, ink-red accent for the active one).

- Fetch `GET /api/cases` on load.
- Click a case → fetch `GET /api/cases/{case_id}/sessions`, expand inline.
- Click a session → fetch `GET /api/sessions/{session_id}`, replace the current chat thread's messages with that history, set `SESSION_ID` state to that session.
- "+ New case" → small form (title, optional crime no / district) → `POST /api/cases` → immediately `POST /api/cases/{case_id}/sessions` to start the first session under it.
- "+ New session" (within an expanded case) → `POST /api/cases/{case_id}/sessions`, clears the chat thread to start fresh under the same case.

### 6.3 Collaborator management — minimal v1

A small "+ Add officer" affordance on an expanded case (visible only to existing collaborators, enforced both client-side for UX and server-side for actual security per Section 5.3) — a single username text input, calling `POST /api/cases/{case_id}/collaborators`. No user-search/autocomplete for v1; officer must know the exact username. `[VERIFY]` whether a simple `GET /api/users?prefix=...` lookup is worth adding for v1.1 — out of scope for this doc's minimum viable version.

---

## 7. Testing / Verification Checklist

Add to the existing chaos/eval suite alongside the language-tagging tests from `PS1_Evidence_Language_Detection.md` Section 7:

- [ ] Create a case as user A → confirm `user_cases:A` contains it, `case:{id}.collaborators == ["A"]`
- [ ] User A adds user B as collaborator → confirm both `case.collaborators` and `user_cases:B` are updated
- [ ] User B (now a collaborator) can `GET /api/cases/{id}/sessions` and see sessions user A created
- [ ] User C (never added) attempts `GET /api/cases/{id}/sessions` → expect 403
- [ ] User A creates two sessions under the same case, sends queries in both concurrently → confirm no history cross-contamination (this is exactly what `get_session_lock`'s existing narrow-scope fix already guards against — this test just confirms it still holds once session creation flows through the new endpoints)
- [ ] Two different users each add a collaborator to two *different* cases at the same time → confirm neither blocks on the other (validates `get_case_lock` is correctly keyed per-case, not a single global lock)
- [ ] Reopening a session via `GET /api/sessions/{id}` after a page refresh restores the exact same history that was visible before refresh
- [ ] A case with zero sessions renders without error in the sidebar (empty state, not a crash)

---

## 8. Open Questions — Deliberately Not Resolved in This Doc

These are policy/product decisions, not technical blockers — flagged rather than silently assumed, consistent with the `[VERIFY]` discipline used throughout this project's other docs:

1. **Should rank grant implicit visibility?** E.g. should a DySP automatically see every case in their district regardless of being added as a collaborator? Section 3 principle 3 currently says no — pure explicit-collaborator visibility — but this is worth a real product conversation, not just a technical default, before treating it as final.
2. **Can a case ever be permanently deleted, or only closed?** This doc assumes closed-not-deleted (Section 4.1), matching the evidentiary-integrity instinct already established in `PS1_Evidence_Language_Detection.md` ("never overwrite the original"), but that's an inference, not something either doc states outright for cases specifically.
3. **Should removing a collaborator be supported in v1**, or only adding? This doc only specs adding (Section 5.3) — removal introduces a harder question (what happens to sessions that officer already created under the case?) that's cleanly separable as a v1.1 addition once the core add/list/view flow is proven out.

---

## 9. Migration Checklist for Antigravity — Exact File Touch List

1. Add `get_case_lock()` to `shared/catalyst_client.py` (Section 5.4) — `[VERIFY]` mirrors `get_session_lock`'s real implementation first
2. Confirm/add `request.state.username` (or equivalent) exposure in `backend/api/middleware/rbac.py` (Section 5.5) — likely blocking prerequisite for everything else in this doc
3. Create `backend/api/routes/cases.py` — `create_case`, `list_cases`, `add_collaborator`, `create_session`, `list_case_sessions` (Sections 5.1–5.3, 5.6–5.7)
4. Create `backend/api/routes/sessions.py` (or fold into `cases.py`) — `get_session_history` (Section 5.8)
5. Register new routers in `backend/main.py` alongside the existing route registrations
6. Modify `backend/api/routes/query.py` — add `_authorize_and_stamp_session` call before `dispatch_query_job` (Section 5.9) — resolve the fire-and-forget-vs-blocking `[VERIFY]` first
7. Remove client-generated `SESSION_ID` from `client/src/App.tsx`; wire session creation through the new endpoints (Section 6.1)
8. Add case/session sidebar UI (Section 6.2) and minimal collaborator-add UI (Section 6.3), styled per existing `index.css` case-file conventions
9. Add the eight test cases from Section 7 to the existing chaos/eval suite
10. Resolve the three open questions in Section 8 with the team before treating this as final, not just before shipping to production

---

## 10. Summary for `agents.md` / Antigravity Context

> New capability: a `Case` object (owner + explicit collaborator list, stored in the existing Catalyst NoSQL table under `case:`/`case_sessions:`/`user_cases:` keys) sits above `Session`. Sessions remain single-officer and reuse the existing `get_session_lock` history-write pattern unchanged. A new `get_case_lock` (same pattern, different key) guards case-metadata writes. Access to any session is entirely inherited from its parent case's collaborator list — sessions have no independent ACL. `session_id` is now server-assigned via `POST /api/cases/{case_id}/sessions`, replacing the current client-generated-UUID-with-no-owner pattern in `App.tsx`. Real-time co-editing of a single session between two officers is explicitly out of scope by design (Section 3) — multi-officer collaboration happens at the case level via independent sessions, not shared live sessions.
