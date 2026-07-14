# PS-1 Phase 5, item 1: Negative Evidence & Exclusion Tracking.
# See Docs/PS1_Negative_Evidence_Exclusion_Tracking.md Section 4.3.
#
# DEVIATIONS from the design doc:
# - officer_id / reversed_by come from request.state.username (populated by
#   RBACMiddleware from the authenticated session), not from the request
#   body. Trusting a client-supplied "who did this" field would let any
#   authenticated officer attribute an exclusion/reversal to someone else --
#   this is exactly the audit trail the whole feature is built to protect.
# - Typed Pydantic request bodies instead of raw `dict`, matching the
#   ExportRequest pattern already used in export.py.
from datetime import datetime, timezone
from typing import Optional
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from shared.exclusion_models import ExclusionRecord, ContradictionRecord
from shared.exclusion_engine import create_exclusion, reverse_exclusion
from shared.catalyst_client import nosql_set  # reused for ContradictionRecord storage

router = APIRouter()


class ExclusionCreateRequest(BaseModel):
    fir_id: str
    accused_id: str
    exclusion_type: str  # "ruled_out" | "alibi_confirmed"
    reason: str
    time_window_start: Optional[str] = None
    time_window_end: Optional[str] = None
    verification_method: Optional[str] = None


class ExclusionReversalRequest(BaseModel):
    reversed_reason: str


class ContradictionCreateRequest(BaseModel):
    evidence_ref: str
    fir_id: str
    reason: str
    contradicting_evidence_ref: Optional[str] = None


def _officer_id(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    return username


@router.post("/api/investigation/exclude")
async def submit_exclusion(payload: ExclusionCreateRequest, request: Request):
    if payload.exclusion_type not in {"ruled_out", "alibi_confirmed"}:
        raise HTTPException(400, "exclusion_type must be 'ruled_out' or 'alibi_confirmed'")
    if payload.exclusion_type == "alibi_confirmed" and (
        not payload.time_window_start or not payload.time_window_end
    ):
        raise HTTPException(400, "alibi_confirmed exclusions require a time window")

    record = ExclusionRecord(
        exclusion_id=str(uuid.uuid4()),
        officer_id=_officer_id(request),
        date=datetime.now(timezone.utc).isoformat(),
        status="active",
        **payload.model_dump(),
    )
    try:
        await create_exclusion(record)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "recorded", "exclusion_id": record.exclusion_id}


@router.post("/api/investigation/exclude/{exclusion_id}/reverse")
async def submit_exclusion_reversal(exclusion_id: str, payload: ExclusionReversalRequest, request: Request):
    try:
        await reverse_exclusion(exclusion_id, _officer_id(request), payload.reversed_reason)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"status": "reversed"}


@router.post("/api/investigation/contradiction")
async def submit_contradiction(payload: ContradictionCreateRequest, request: Request):
    record = ContradictionRecord(
        contradiction_id=str(uuid.uuid4()),
        officer_id=_officer_id(request),
        date=datetime.now(timezone.utc).isoformat(),
        status="active",
        **payload.model_dump(),
    )
    await nosql_set(f"contradiction:{record.contradiction_id}", record.model_dump_json())
    return {"status": "recorded", "contradiction_id": record.contradiction_id}
