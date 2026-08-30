# PS-1 Phase 5, item 3: Case & Session Management Layer.
# See Docs/PS1_Case_Session_Management.md Section 5.
#
# SCOPE NOTE: this file implements the case/session data model and CRUD
# routes only. It deliberately does NOT touch backend/api/routes/query.py
# (Section 5.9) or the frontend (Section 6) -- session_id there is still the
# client-generated UUID v4 the current frontend already depends on for the
# live chat feature. Making /api/query require a case-scoped, server-issued
# session_id is a breaking change to that contract and needs to land together
# with the frontend rewiring that adopts it, not ahead of it.
import json
import secrets
import time
import uuid
import asyncio
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.catalyst_client import nosql_get, nosql_set, get_case_lock, get_lock, nosql_delete
from shared.auth import get_user
from shared.hypothesis_models import HypothesisRecord
from shared.hypothesis_engine import create_hypothesis, list_hypotheses_by_case


async def _nosql_get_stable(key: str, retries: int = 2, delay: float = 0.35):
    """nosql_get with a couple of retries on a None result.

    Catalyst NoSQL is eventually consistent: a `case:{id}` / `session_meta:{id}`
    doc written moments ago can briefly read back as absent, which made
    `list_cases` / `list_case_sessions` drop rows and "flicker" between
    refreshes. A short retry papers over that lag without masking a genuine
    delete (a truly absent key just returns None after the retries).
    """
    doc = await nosql_get(key)
    for _ in range(retries):
        if doc is not None:
            return doc
        await asyncio.sleep(delay)
        doc = await nosql_get(key)
    return doc

router = APIRouter()

# ── Board card layout (Phase 4) ─────────────────────────────────────────────
# case_board_layout:{case_id} is a single mutable doc holding WHERE cards sit on
# the corkboard. It is deliberately separate from the append-only pin log
# case_board:{case_id} (WHAT was pinned, with audit fields). Full-replace on PUT
# plus a client-side debounce is enough at this scale; no per-card PATCH in v1.
_COLOR_RE = r"^(#[0-9a-fA-F]{3,8}|[a-zA-Z-]{1,24}|var\(--[a-z0-9-]{1,40}\))$"
_MAX_CARDS = 200


class BoardCardModel(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    kind: Literal["hypothesis", "suspect", "fir", "note"]
    refId: Optional[str] = Field(None, max_length=128)
    x: float
    y: float
    w: float
    h: float
    color: str = Field(pattern=_COLOR_RE, max_length=64)
    rotation: Optional[float] = None
    text: Optional[str] = Field(None, max_length=2000)
    connections: List[str] = Field(default_factory=list, max_length=50)


class BoardLayoutPutRequest(BaseModel):
    cards: List[BoardCardModel] = Field(default_factory=list, max_length=_MAX_CARDS)


class CaseHypothesisCreateRequest(BaseModel):
    statement: str = Field(max_length=2000)
    detail: Optional[str] = Field(None, max_length=8000)
    linked_entity_ids: List[str] = Field(default_factory=list, max_length=100)
    fir_id: Optional[str] = Field(None, max_length=128)


class CreateCaseRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    crime_no: str | None = Field(None, max_length=40)
    district: str | None = Field(None, max_length=60)


class AddCollaboratorRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)


class PinItemRequest(BaseModel):
    source_session_id: str
    content_type: str
    content: dict


async def _require_collaborator(case_id: str, username: str) -> dict:
    doc = await nosql_get(f"case:{case_id}")
    if not doc:
        raise HTTPException(403, "Not authorized for this case")
    case = json.loads(doc["value"])
    if username not in case["collaborators"]:
        raise HTTPException(403, "Not authorized for this case")
    return case


async def _add_case_to_user_index(username: str, case_id: str):
    async with get_lock(f"user_cases:{username}"):
        doc = await nosql_get(f"user_cases:{username}")
        case_ids = json.loads(doc["value"]) if doc else []
        if case_id not in case_ids:
            case_ids.append(case_id)
            await nosql_set(f"user_cases:{username}", json.dumps(case_ids))

async def _remove_case_from_user_index(username: str, case_id: str):
    async with get_lock(f"user_cases:{username}"):
        doc = await nosql_get(f"user_cases:{username}")
        if doc:
            case_ids = json.loads(doc["value"])
            if case_id in case_ids:
                case_ids.remove(case_id)
                await nosql_set(f"user_cases:{username}", json.dumps(case_ids))

@router.post("/api/cases")
async def create_case(body: CreateCaseRequest, request: Request):
    username = request.state.username
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
    await _add_case_to_user_index(username, case_id)

    return case


@router.get("/api/cases")
async def list_cases(request: Request):
    username = request.state.username
    user_cases_doc = await nosql_get(f"user_cases:{username}")
    case_ids = json.loads(user_cases_doc["value"]) if user_cases_doc else []

    cases = []
    if case_ids:
        case_docs = await asyncio.gather(*(_nosql_get_stable(f"case:{cid}") for cid in case_ids))
        cases = [json.loads(doc["value"]) for doc in case_docs if doc]

    cases.sort(key=lambda c: c.get("last_activity_at", 0), reverse=True)
    return {"cases": cases}


@router.delete("/api/cases/{case_id}")
async def delete_case(case_id: str, request: Request):
    username = request.state.username
    async with get_case_lock(case_id):
        case = await _require_collaborator(case_id, username)
        
        # Remove from all collaborators' indexes
        for collab in case.get("collaborators", []):
            await _remove_case_from_user_index(collab, case_id)

        # Delete all sessions associated with this case
        sessions_doc = await nosql_get(f"case_sessions:{case_id}")
        session_ids = json.loads(sessions_doc["value"]) if sessions_doc else []
        
        delete_tasks = []
        for sid in session_ids:
            delete_tasks.append(nosql_delete(f"session_meta:{sid}"))
            delete_tasks.append(nosql_delete(f"history:{sid}"))
            
        delete_tasks.extend([
            nosql_delete(f"case_sessions:{case_id}"),
            nosql_delete(f"case_board:{case_id}"),
            nosql_delete(f"case_board_layout:{case_id}"),
            nosql_delete(f"hypotheses_by_case:{case_id}"),
            nosql_delete(f"case:{case_id}")
        ])
        
        if delete_tasks:
            await asyncio.gather(*delete_tasks)
        
    return {"status": "deleted"}


@router.post("/api/cases/{case_id}/collaborators")
async def add_collaborator(case_id: str, body: AddCollaboratorRequest, request: Request):
    requester = request.state.username
    async with get_case_lock(case_id):
        case = await _require_collaborator(case_id, requester)

        if not await get_user(body.username):
            raise HTTPException(404, "Officer not found in system")

        if body.username not in case["collaborators"]:
            case["collaborators"].append(body.username)
            await nosql_set(f"case:{case_id}", json.dumps(case))

    # BUG FIX: moved outside the get_case_lock(case_id) block and into
    # _add_case_to_user_index's own get_lock(f"user_cases:{username}") --
    # this update touches the TARGET user's index, not this case's document,
    # so guarding it with only the case lock let two concurrent
    # add_collaborator calls for the same officer on two different cases
    # race each other (see _add_case_to_user_index's docstring above).
    await _add_case_to_user_index(body.username, case_id)

    return case


@router.post("/api/cases/{case_id}/sessions")
async def create_case_session(case_id: str, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)

    session_id = f"s_{secrets.token_hex(4)}"
    now = time.time()
    meta = {
        "session_id": session_id,
        "case_id": case_id,
        "created_by": username,
        "created_at": now,
        "title": None,  # set on the session's first query
        "last_activity_at": now,
    }
    await nosql_set(f"session_meta:{session_id}", json.dumps(meta))

    async with get_case_lock(case_id):
        sessions_doc = await nosql_get(f"case_sessions:{case_id}")
        sessions = json.loads(sessions_doc["value"]) if sessions_doc else []
        sessions.append(session_id)
        await nosql_set(f"case_sessions:{case_id}", json.dumps(sessions))

    return meta


@router.get("/api/cases/{case_id}/sessions")
async def list_case_sessions(case_id: str, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)

    sessions_doc = await nosql_get(f"case_sessions:{case_id}")
    session_ids = json.loads(sessions_doc["value"]) if sessions_doc else []

    sessions = []
    if session_ids:
        meta_docs = await asyncio.gather(*(_nosql_get_stable(f"session_meta:{sid}") for sid in session_ids))
        sessions = [json.loads(doc["value"]) for doc in meta_docs if doc]

    sessions.sort(key=lambda s: s.get("last_activity_at", 0), reverse=True)
    return {"sessions": sessions}


@router.post("/api/cases/{case_id}/board")
async def pin_to_case_board(case_id: str, body: PinItemRequest, request: Request):
    username = request.state.username
    async with get_case_lock(case_id):
        await _require_collaborator(case_id, username)
        board_doc = await nosql_get(f"case_board:{case_id}")
        board = json.loads(board_doc["value"]) if board_doc else []
        board.append({
            "pinned_by": username,
            "pinned_at": time.time(),
            "source_session_id": body.source_session_id,
            "content_type": body.content_type,
            "content": body.content,
        })
        await nosql_set(f"case_board:{case_id}", json.dumps(board))
    return {"status": "pinned"}


@router.get("/api/cases/{case_id}/board")
async def get_case_board(case_id: str, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)
    board_doc = await nosql_get(f"case_board:{case_id}")
    return {"board": json.loads(board_doc["value"]) if board_doc else []}


@router.get("/api/cases/{case_id}/board/layout")
async def get_case_board_layout(case_id: str, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)
    layout_doc = await nosql_get(f"case_board_layout:{case_id}")
    if not layout_doc:
        return {"cards": []}
    return {"cards": json.loads(layout_doc["value"]).get("cards", [])}


@router.put("/api/cases/{case_id}/board/layout")
async def put_case_board_layout(case_id: str, body: BoardLayoutPutRequest, request: Request):
    username = request.state.username
    async with get_case_lock(case_id):
        await _require_collaborator(case_id, username)
        doc = {
            "cards": [c.model_dump() for c in body.cards],
            "updated_at": time.time(),
            "updated_by": username,
        }
        await nosql_set(f"case_board_layout:{case_id}", json.dumps(doc))
    return {"cards": doc["cards"]}


@router.get("/api/cases/{case_id}/hypotheses")
async def get_case_hypotheses(case_id: str, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)
    records = await list_hypotheses_by_case(case_id)
    return {"hypotheses": records}


@router.post("/api/cases/{case_id}/hypotheses")
async def create_case_hypothesis(case_id: str, body: CaseHypothesisCreateRequest, request: Request):
    username = request.state.username
    await _require_collaborator(case_id, username)

    if not body.statement.strip():
        raise HTTPException(400, "Statement cannot be empty")

    # The hypothesis engine's Cypher check traverses linked_entity_ids, not
    # fir_id, but fir_id is still required by the model -- with no specific FIR,
    # fall back to the case_id (generalises the old 'DEMO_CASE_001' fallback).
    fir_id = (body.fir_id or "").strip() or case_id

    record = HypothesisRecord(
        hypothesis_id=str(uuid.uuid4()),
        fir_id=fir_id,
        case_id=case_id,
        officer_id=username,
        statement=body.statement,
        detail=body.detail,
        linked_entity_ids=body.linked_entity_ids,
        status="open",
        created_date=datetime.now(timezone.utc).isoformat(),
    )
    await create_hypothesis(record)
    return {"status": "created", "hypothesis": record}
