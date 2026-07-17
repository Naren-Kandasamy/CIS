from fastapi import APIRouter, Request, HTTPException
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from shared.review_queue_engine import get_pending_review_items, get_review_item, push_review_item
from shared.catalyst_client import nosql_set

router = APIRouter(tags=["Review Queue"])

class ResolvePayload(BaseModel):
    status: str

@router.get("/api/review-queue")
async def list_review_queue(request: Request, fir_id: Optional[str] = None):
    """
    List pending review queue alerts for an officer.
    """
    items = await get_pending_review_items(fir_id)
    return {"items": [item.model_dump() for item in items]}

@router.post("/api/review-queue/{item_id}/resolve")
async def resolve_review_item(item_id: str, payload: ResolvePayload, request: Request):
    """
    Mark a review queue alert as reviewed or dismissed.
    """
    if payload.status not in {"reviewed", "dismissed"}:
        raise HTTPException(status_code=400, detail="Invalid status. Must be 'reviewed' or 'dismissed'.")

    # Get officer username from RBAC middleware
    username = getattr(request.state, "username", "unknown_officer")
    
    item = await get_review_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Review item not found.")
        
    item.status = payload.status
    item.reviewed_by = username
    item.reviewed_date = datetime.now(timezone.utc).isoformat()
    
    # Save updated item back to DB (no need to update index as the index holds IDs)
    await nosql_set(f"review_queue:{item.item_id}", item.model_dump_json())
    
    return {"status": "success", "item": item.model_dump()}
