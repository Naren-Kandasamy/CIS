from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import record_feedback_event
from shared.catalyst_client import nosql_get, nosql_set, get_lock
from datetime import datetime, timezone
import uuid

router = APIRouter()

# BUG FIX: `payload: dict` accepted any JSON shape untyped, so a type-confused
# field (e.g. session_id sent as a JSON number) sailed past the only
# validation present (the verdict check below) and crashed inside
# CorrectionEvent(...) construction with an unhandled pydantic.ValidationError
# -- main.py registers no handler for that exception, so Starlette's default
# ServerErrorMiddleware turned it into a generic 500. A typed request model
# makes FastAPI validate and reject malformed input with a normal 422 before
# the handler body ever runs.
class FeedbackCorrectionRequest(BaseModel):
    session_id: str = "unknown_session"
    query_text: str = ""
    edge_type: str = "UNKNOWN"
    crime_type: Optional[str] = None
    edge_id: Optional[str] = None
    verdict: str
    explanation: Optional[str] = None

# BUG FIX: this route had no rate limit, dedup, or diversity check, so any
# single authenticated officer (any rank -- this route has no ROUTE_MIN_ROLE
# entry) could script an unbounded loop of corrections and (a) grow the
# correction:<uuid> NoSQL table without bound, and (b) repeatedly
# read-modify-write the broad trust:<edge_type> counter that
# get_trust_weight() (shared/feedback_engine.py) feeds into every officer's
# every future confidence score. Cap submissions per officer+edge_type within
# a rolling window, using a TTL'd NoSQL counter (self-expires instead of
# growing unbounded) guarded by the existing per-key lock so concurrent
# requests from the same officer can't race the read-modify-write.
# NOTE: this only slows a scripted spam run; it cannot fully close the
# finding on its own. Requiring a minimum number of *distinct* officer/session
# contributors before a broad trust score can move materially, and putting a
# TTL/archival policy on correction:<uuid> records, both live in
# record_feedback_event()/get_trust_weight() (shared/feedback_engine.py) --
# out of scope for a fix confined to this file.
FEEDBACK_RATE_LIMIT = 10
FEEDBACK_RATE_WINDOW_SECONDS = 3600

def _officer_id(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    return username

async def _enforce_rate_limit(officer_id: str, edge_type: str):
    key = f"feedback_rate:{officer_id}:{edge_type}"
    async with get_lock(key):
        existing = await nosql_get(key)
        count = int(existing["value"]) if existing else 0
        if count >= FEEDBACK_RATE_LIMIT:
            raise HTTPException(
                429,
                f"Feedback rate limit exceeded for edge_type '{edge_type}' -- "
                f"max {FEEDBACK_RATE_LIMIT} submissions per {FEEDBACK_RATE_WINDOW_SECONDS}s"
            )
        await nosql_set(key, str(count + 1), ttl=FEEDBACK_RATE_WINDOW_SECONDS)

@router.post("/api/feedback/correction")
async def submit_feedback(payload: FeedbackCorrectionRequest, request: Request):
    if payload.verdict not in {"confirmed", "corrected"}:
        raise HTTPException(400, "verdict must be 'confirmed' or 'corrected'")

    officer_id = _officer_id(request)
    await _enforce_rate_limit(officer_id, payload.edge_type)

    event = CorrectionEvent(
        event_id=str(uuid.uuid4()),
        session_id=payload.session_id,
        officer_id=officer_id,
        timestamp=datetime.now(timezone.utc).isoformat(),
        query_text=payload.query_text,
        edge_type=payload.edge_type,
        crime_type=payload.crime_type,
        edge_id=payload.edge_id,
        verdict=payload.verdict,
        explanation=payload.explanation
    )

    await record_feedback_event(event)
    return {"status": "recorded"}
