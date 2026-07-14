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

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.catalyst_client import nosql_get, nosql_set, get_case_lock
from shared.auth import get_user

router = APIRouter()


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


async def _get_case_or_404(case_id: str) -> dict:
    doc = await nosql_get(f"case:{case_id}")
    if not doc:
        raise HTTPException(404, "Case not found")
    return json.loads(doc["value"])


async def _require_collaborator(case_id: str, username: str) -> dict:
    case = await _get_case_or_404(case_id)
    if username not in case["collaborators"]:
        raise HTTPException(403, "Not a collaborator on this case")
    return case


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

    user_cases_doc = await nosql_get(f"user_cases:{username}")
    user_cases = json.loads(user_cases_doc["value"]) if user_cases_doc else []
    user_cases.append(case_id)
    await nosql_set(f"user_cases:{username}", json.dumps(user_cases))

    return case


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

            target_cases_doc = await nosql_get(f"user_cases:{body.username}")
            target_cases = json.loads(target_cases_doc["value"]) if target_cases_doc else []
            if case_id not in target_cases:
                target_cases.append(case_id)
                await nosql_set(f"user_cases:{body.username}", json.dumps(target_cases))

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
    for sid in session_ids:
        meta_doc = await nosql_get(f"session_meta:{sid}")
        if meta_doc:
            sessions.append(json.loads(meta_doc["value"]))
    sessions.sort(key=lambda s: s["last_activity_at"], reverse=True)
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
