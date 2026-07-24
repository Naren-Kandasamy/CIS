from fastapi import APIRouter, HTTPException, Request
from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import record_feedback_event

router = APIRouter()

@router.post("/api/feedback/correction")
async def submit_feedback(event: CorrectionEvent, request: Request):
    if event.verdict not in {"confirmed", "corrected"}:
        raise HTTPException(status_code=400, detail="verdict must be 'confirmed' or 'corrected'")
    
    await record_feedback_event(event)
    return {"status": "recorded"}
