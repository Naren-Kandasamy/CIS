# PS-1 Phase 5, item 3: Case & Session Management Layer.
# See Docs/PS1_Case_Session_Management.md Section 5.8.
import json

from fastapi import APIRouter, HTTPException, Request

from shared.catalyst_client import nosql_get
from backend.api.routes.cases import _require_collaborator

router = APIRouter()


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
