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
from pydantic import BaseModel, Field, field_validator, model_validator

from shared.exclusion_models import ExclusionRecord, ContradictionRecord
from shared.exclusion_engine import create_exclusion, reverse_exclusion
from shared.catalyst_client import nosql_set  # reused for ContradictionRecord storage

router = APIRouter()


def _validate_iso_datetime(value, field_name):
    if value is None:
        return value
    try:
        datetime.fromisoformat(value)
    except ValueError:
        raise ValueError(f"{field_name} must be a valid ISO 8601 datetime, got {value!r}")
    return value


class ExclusionCreateRequest(BaseModel):
    fir_id: str = Field(max_length=128)
    accused_id: str = Field(max_length=128)
    exclusion_type: str  # "ruled_out" | "alibi_confirmed"
    reason: str = Field(max_length=1000)
    time_window_start: Optional[str] = Field(default=None, max_length=64)
    time_window_end: Optional[str] = Field(default=None, max_length=64)
    verification_method: Optional[str] = Field(default=None, max_length=256)

    @field_validator("time_window_start", "time_window_end")
    @classmethod
    def _check_iso_format(cls, v, info):
        return _validate_iso_datetime(v, info.field_name)

    @model_validator(mode="after")
    def _check_window_order(self):
        if self.time_window_start and self.time_window_end and self.time_window_start > self.time_window_end:
            raise ValueError("time_window_start must not be after time_window_end")
        return self


class ExclusionReversalRequest(BaseModel):
    reversed_reason: str = Field(max_length=1000)


class ContradictionCreateRequest(BaseModel):
    evidence_ref: str = Field(max_length=256)
    fir_id: str = Field(max_length=128)
    reason: str = Field(max_length=1000)
    contradicting_evidence_ref: Optional[str] = Field(default=None, max_length=256)


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
        # BUG FIX: create_exclusion can now also raise for "an active
        # exclusion already exists for this pair" (see
        # shared/exclusion_engine.py) -- that's a conflict, not a
        # not-found, so map it to 409 instead of blanket 404.
        status = 409 if "already exists" in str(e) else 404
        raise HTTPException(status, str(e))
    return {"status": "recorded", "exclusion_id": record.exclusion_id}


@router.post("/api/investigation/exclude/{exclusion_id}/reverse")
async def submit_exclusion_reversal(exclusion_id: str, payload: ExclusionReversalRequest, request: Request):
    try:
        await reverse_exclusion(exclusion_id, _officer_id(request), payload.reversed_reason)
    except ValueError as e:
        # BUG FIX: reverse_exclusion can now also raise for "already
        # reversed" (see shared/exclusion_engine.py) -- a conflict, not a
        # not-found, so map it to 409 instead of blanket 404.
        status = 409 if "is not active" in str(e) else 404
        raise HTTPException(status, str(e))
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
