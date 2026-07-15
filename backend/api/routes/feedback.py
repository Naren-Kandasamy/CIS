from fastapi import APIRouter, HTTPException, Request
from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import record_feedback_event
from datetime import datetime, timezone
import uuid

router = APIRouter()

def _officer_id(request: Request) -> str:
    username = getattr(request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    return username

@router.post("/api/feedback/correction")
async def submit_feedback(payload: dict, request: Request):
    verdict = payload.get("verdict")
    if verdict not in {"confirmed", "corrected"}:
        raise HTTPException(400, "verdict must be 'confirmed' or 'corrected'")
    
    event = CorrectionEvent(
        event_id=str(uuid.uuid4()),
        session_id=payload.get("session_id", "unknown_session"),
        officer_id=_officer_id(request),
        timestamp=datetime.now(timezone.utc).isoformat(),
        query_text=payload.get("query_text", ""),
        edge_type=payload.get("edge_type", "UNKNOWN"),
        crime_type=payload.get("crime_type"),
        edge_id=payload.get("edge_id"),
        verdict=verdict,
        explanation=payload.get("explanation")
    )
    
    await record_feedback_event(event)
    return {"status": "recorded"}
