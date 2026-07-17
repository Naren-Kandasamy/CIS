import json
from shared.catalyst_client import nosql_set, nosql_get
from shared.review_queue_models import ReviewQueueItem

async def push_review_item(item: ReviewQueueItem):
    # Save the actual item
    await nosql_set(f"review_queue:{item.item_id}", item.model_dump_json())
    
    # Maintain an index of review queue item IDs since Catalyst KV doesn't support prefix queries natively
    index_data = await nosql_get("review_queue_index")
    index = json.loads(index_data["value"]) if index_data else []
    if item.item_id not in index:
        index.append(item.item_id)
        await nosql_set("review_queue_index", json.dumps(index))

async def get_pending_review_items(fir_id: str | None = None) -> list[ReviewQueueItem]:
    index_data = await nosql_get("review_queue_index")
    index = json.loads(index_data["value"]) if index_data else []
    
    items = []
    for item_id in index:
        raw = await nosql_get(f"review_queue:{item_id}")
        if raw:
            items.append(json.loads(raw["value"]))
            
    parsed = [ReviewQueueItem(**i) for i in items]
    parsed = [i for i in parsed if i.status == "pending"]
    if fir_id:
        parsed = [i for i in parsed if i.fir_id == fir_id or i.related_fir_id == fir_id]
    
    # Sort newest first
    parsed.sort(key=lambda x: x.created_date, reverse=True)
    return parsed

async def get_review_item(item_id: str) -> ReviewQueueItem | None:
    raw = await nosql_get(f"review_queue:{item_id}")
    if raw:
        return ReviewQueueItem(**json.loads(raw["value"]))
    return None
