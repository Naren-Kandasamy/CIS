# PS-1 Phase 5, Item 1.2: Review Queue Engine
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.2.

import json
import logging
from datetime import datetime, timezone
from typing import Optional
from shared.catalyst_client import nosql_get, nosql_set, nosql_query_by_prefix
from shared.review_queue_models import ReviewQueueItem

logger = logging.getLogger(__name__)

async def push_review_item(item: ReviewQueueItem):
    """Upsert a review queue item into NoSQL."""
    try:
        data_str = item.model_dump_json()
    except AttributeError:
        data_str = item.json()
    await nosql_set(f"review_queue:{item.item_id}", data_str)

async def get_pending_review_items(fir_id: Optional[str] = None) -> list[ReviewQueueItem]:
    """Retrieve all pending review queue items, optionally filtered by FIR ID or related FIR ID."""
    items = await nosql_query_by_prefix("review_queue:")
    parsed = []
    for i in items:
        try:
            parsed.append(ReviewQueueItem(**i))
        except Exception as e:
            # FIXED S-2: log at ERROR level so this surfaces in production monitoring.
            # A silent print was previously dropping corrupt records invisibly.
            logger.error(
                "Failed to parse ReviewQueueItem from NoSQL — record may be corrupt. "
                "Consider moving it to a quarantine key (e.g. 'review_queue_corrupt:'). "
                "Raw data: %s. Error: %s",
                i, e
            )
            
    # Filter pending only
    parsed = [i for i in parsed if i.status == "pending"]
    if fir_id:
        parsed = [i for i in parsed if i.fir_id == fir_id or i.related_fir_id == fir_id]
    return parsed

async def resolve_review_item(item_id: str, status: str, officer_id: str) -> Optional[ReviewQueueItem]:
    """Resolve a review queue item by updating its status and adding reviewer details."""
    if status not in {"reviewed", "dismissed"}:
        raise ValueError("Status must be 'reviewed' or 'dismissed'")
        
    raw = await nosql_get(f"review_queue:{item_id}")
    if not raw or "value" not in raw:
        return None
        
    try:
        data = json.loads(raw["value"])
        item = ReviewQueueItem(**data)
    except Exception as e:
        print(f"Error parsing retrieved ReviewQueueItem for resolution: {e}")
        return None
        
    item.status = status
    item.reviewed_by = officer_id
    item.reviewed_date = datetime.now(timezone.utc).isoformat()
    
    await push_review_item(item)
    return item
