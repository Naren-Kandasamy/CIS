# PS-1 Phase 5, Item 7: Hypothesis Workspace API Routes
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 7.3.

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shared.hypothesis_models import HypothesisRecord
from shared.hypothesis_engine import (
    create_hypothesis,
    get_hypothesis,
    list_hypotheses,
    check_hypothesis,
    resolve_hypothesis,
)

router = APIRouter()


class HypothesisCreateRequest(BaseModel):
    fir_id: str
    statement: str
    linked_entity_ids: List[str] = []


class HypothesisResolveRequest(BaseModel):
    status: str  # "confirmed" | "refuted"
    resolved_reason: str


def _officer_id(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    return username


@router.post("/api/investigation/hypothesis")
async def create_hypothesis_endpoint(payload: HypothesisCreateRequest, request: Request):
    if not payload.statement.strip():
        raise HTTPException(400, "Statement cannot be empty")
    if not payload.fir_id.strip():
        raise HTTPException(400, "fir_id cannot be empty")

    record = HypothesisRecord(
        hypothesis_id=str(uuid.uuid4()),
        fir_id=payload.fir_id,
        officer_id=_officer_id(request),
        statement=payload.statement,
        linked_entity_ids=payload.linked_entity_ids,
        status="open",
        created_date=datetime.now(timezone.utc).isoformat(),
    )
    await create_hypothesis(record)
    return {"status": "created", "hypothesis": record}


@router.get("/api/investigation/hypothesis/{fir_id}")
async def list_hypotheses_endpoint(fir_id: str, request: Request):
    _officer_id(request)
    records = await list_hypotheses(fir_id)
    return {"fir_id": fir_id, "hypotheses": records}


@router.post("/api/investigation/hypothesis/{hypothesis_id}/check")
async def check_hypothesis_endpoint(hypothesis_id: str, request: Request):
    _officer_id(request)
    try:
        log = await check_hypothesis(hypothesis_id)
        return {"status": "checked", "log": log}
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.post("/api/investigation/hypothesis/{hypothesis_id}/resolve")
async def resolve_hypothesis_endpoint(hypothesis_id: str, payload: HypothesisResolveRequest, request: Request):
    if payload.status not in {"confirmed", "refuted"}:
        raise HTTPException(400, "status must be 'confirmed' or 'refuted'")
    if not payload.resolved_reason.strip():
        raise HTTPException(400, "resolved_reason cannot be empty")

    officer = _officer_id(request)
    try:
        record = await resolve_hypothesis(
            hypothesis_id=hypothesis_id,
            status=payload.status,
            resolved_by=officer,
            resolved_reason=payload.resolved_reason,
        )
        return {"status": "resolved", "hypothesis": record}
    except ValueError as e:
        raise HTTPException(404, str(e))
