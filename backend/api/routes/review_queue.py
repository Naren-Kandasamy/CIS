# PS-1 Phase 5, Item 1.2: Review Queue API Routes
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.2.

from fastapi import APIRouter, HTTPException
from typing import Optional
from shared.review_queue_engine import get_pending_review_items, resolve_review_item

router = APIRouter()

@router.get("/api/review-queue")
async def list_review_queue(fir_id: Optional[str] = None):
    try:
        items = await get_pending_review_items(fir_id)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/review-queue/{item_id}/resolve")
async def resolve_review_item_endpoint(item_id: str, payload: dict):
    # payload: {"status": "reviewed" | "dismissed", "reviewed_by": str}
    status = payload.get("status")
    reviewed_by = payload.get("reviewed_by")
    
    if not status or not reviewed_by:
        raise HTTPException(status_code=400, detail="Missing 'status' or 'reviewed_by' in payload.")
        
    if status not in {"reviewed", "dismissed"}:
        raise HTTPException(status_code=400, detail="Status must be 'reviewed' or 'dismissed'.")
        
    try:
        item = await resolve_review_item(item_id, status, reviewed_by)
        if not item:
            raise HTTPException(status_code=404, detail=f"Review queue item {item_id} not found.")
        return item
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
