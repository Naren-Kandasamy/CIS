# PS-1 Phase 5, item 3: Case & Session Management Layer.
# See Docs/PS1_Case_Session_Management.md Section 5.8.
import json
import asyncio
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.catalyst_client import nosql_get, nosql_set, nosql_delete, get_case_lock
from backend.api.routes.cases import _require_collaborator

router = APIRouter()


class SessionPatchRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)


@router.get("/api/sessions/{session_id}")
async def get_session_history(session_id: str, request: Request):
    username = request.state.username
    meta_doc = await nosql_get(f"session_meta:{session_id}")
    if not meta_doc:
        raise HTTPException(404, "Session not found")
    meta = json.loads(meta_doc["value"])

    # Access is inherited entirely from the parent case's collaborator list --
    # a session has no independent ACL of its own.
    await _require_collaborator(meta["case_id"], username)

    history_doc = await nosql_get(f"history:{session_id}")
    history = json.loads(history_doc["value"]) if history_doc else []
    return {"meta": meta, "history": history}


@router.patch("/api/sessions/{session_id}")
async def patch_session(session_id: str, body: SessionPatchRequest, request: Request):
    """Rename a session. Used by the client to stamp a session's title from the
    officer's first query (session_meta.title starts as None at creation)."""
    username = request.state.username
    meta_doc = await nosql_get(f"session_meta:{session_id}")
    if not meta_doc:
        raise HTTPException(404, "Session not found")
    meta = json.loads(meta_doc["value"])
    case_id = meta["case_id"]

    async with get_case_lock(case_id):
        await _require_collaborator(case_id, username)
        # Re-read inside the lock to avoid clobbering a concurrent update.
        meta_doc = await nosql_get(f"session_meta:{session_id}")
        meta = json.loads(meta_doc["value"])
        meta["title"] = body.title.strip()
        meta["last_activity_at"] = time.time()
        await nosql_set(f"session_meta:{session_id}", json.dumps(meta))

    return meta


@router.delete("/api/sessions/{session_id}")
async def delete_session(session_id: str, request: Request):
    username = request.state.username
    meta_doc = await nosql_get(f"session_meta:{session_id}")
    if not meta_doc:
        raise HTTPException(404, "Session not found")
    meta = json.loads(meta_doc["value"])
    case_id = meta["case_id"]

    async with get_case_lock(case_id):
        await _require_collaborator(case_id, username)
        
        # Remove from case's session list
        sessions_doc = await nosql_get(f"case_sessions:{case_id}")
        if sessions_doc:
            sessions = json.loads(sessions_doc["value"])
            if session_id in sessions:
                sessions.remove(session_id)
                await nosql_set(f"case_sessions:{case_id}", json.dumps(sessions))
                
        # Delete session data in parallel
        await asyncio.gather(
            nosql_delete(f"session_meta:{session_id}"),
            nosql_delete(f"history:{session_id}")
        )
        
    return {"status": "deleted"}

