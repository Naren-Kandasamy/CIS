# PS-1 Phase 5, Item 1.2: Review Queue API Routes
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.2.

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Literal, Optional
from shared.review_queue_engine import get_pending_review_items, resolve_review_item

router = APIRouter()


class ResolvePayload(BaseModel):
    # FIXED B-2: typed Pydantic model for strict validation instead of raw dict.
    # FastAPI returns 422 automatically when field types or values are invalid.
    status: Literal["reviewed", "dismissed"]
    # reviewed_by is optional here — the route will override it with the RBAC session user.
    # Kept in model so callers can still read back who reviewed (from the returned item).


@router.get("/api/review-queue")
async def list_review_queue(fir_id: Optional[str] = None):
    try:
        items = await get_pending_review_items(fir_id)
        return items
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/review-queue/{item_id}/resolve")
async def resolve_review_item_endpoint(item_id: str, payload: ResolvePayload, request: Request):
    # FIXED B-3: extract officer identity from the RBAC-authenticated session state,
    # not from the request body — preventing any user from forging another officer's
    # name in the audit trail. The RBACMiddleware injects username/role into
    # scope["state"] (accessed as request.state.username).
    officer_id = getattr(request.state, "username", "unknown")

    try:
        item = await resolve_review_item(item_id, payload.status, officer_id)
    except ValueError as val_err:
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    # FIXED: raise 404 AFTER the try/except block, not inside it,
    # so the broad `except Exception` clause cannot intercept it.
    if not item:
        raise HTTPException(status_code=404, detail=f"Review queue item '{item_id}' not found.")

    return item
