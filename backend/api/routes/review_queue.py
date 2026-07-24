from fastapi import APIRouter, Request, HTTPException
from typing import Optional
from datetime import datetime, timezone
from pydantic import BaseModel
from shared.review_queue_engine import get_pending_review_items, get_review_item, push_review_item
from shared.catalyst_client import nosql_set, get_lock

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

    # BUG FIX: the get_review_item/mutate/nosql_set sequence below was an
    # unlocked read-modify-write, same class of bug push_review_item's index
    # update already guards with get_lock("review_queue_index"). Two officers
    # resolving the same item_id concurrently (or one officer re-resolving an
    # already-resolved item) would each read a stale in-memory copy and the
    # last write would silently clobber the other's status/reviewed_by, with
    # no error to either caller. Serialize per-item and re-check status
    # (fetched inside the lock, not the stale copy from before acquiring it)
    # so a second resolve on a non-pending item gets a 409 instead of
    # overwriting the prior officer's decision.
    async with get_lock(f"review_queue_item:{item_id}"):
        item = await get_review_item(item_id)
        if not item:
            raise HTTPException(status_code=404, detail="Review item not found.")

        if item.status != "pending":
            raise HTTPException(status_code=409, detail="Item already resolved.")

        item.status = payload.status
        item.reviewed_by = username
        item.reviewed_date = datetime.now(timezone.utc).isoformat()

        # Save updated item back to DB (no need to update index as the index holds IDs)
        await nosql_set(f"review_queue:{item.item_id}", item.model_dump_json())

    return {"status": "success", "item": item.model_dump()}
