import asyncio
import json
from shared.catalyst_client import nosql_set, nosql_get, get_lock
from shared.review_queue_models import ReviewQueueItem

async def push_review_item(item: ReviewQueueItem):
    # Save the actual item
    await nosql_set(f"review_queue:{item.item_id}", item.model_dump_json())

    # Maintain an index of review queue item IDs since Catalyst KV doesn't support prefix queries natively.
    # BUG FIX: this read-modify-write raced when two items were pushed
    # concurrently (e.g. a cold-case-match scan pushing several alerts at
    # once) -- both readers could see the same stale index and the second
    # write would silently clobber the first append. Same bug class already
    # fixed once for session history (get_session_lock) and once for case
    # metadata (get_case_lock); a single shared lock is enough here since
    # there's only one global index, not one per key.
    # BUG FIX: get_lock() only serializes coroutines inside this one warm
    # process/container -- across separate AppSail instances, two
    # near-simultaneous push_review_item calls (e.g. a cold-case-match scan
    # on one instance and an ANPR wanted-hit on another) can both read the
    # same index snapshot and both nosql_set() it back, so whichever write
    # lands last silently drops the other's item_id forever (the item's own
    # data row still exists but is never listed again, with no error).
    # Catalyst's NoSQL REST API has no conditional/compare-and-set write in
    # this SDK version (see _nosql_request), so the write itself can't be
    # made atomic; instead we re-read right before each write and verify
    # after writing that our own id actually stuck, retrying (which also
    # re-merges anything a concurrent writer added in the meantime) if not.
    # This narrows the loss window from "any overlap across the whole
    # critical section" to "both instances' final read+write landing in the
    # same few-ms slice" -- not a full guarantee, but a large reduction.
    async with get_lock("review_queue_index"):
        max_attempts = 5
        for attempt in range(max_attempts):
            index_data = await nosql_get("review_queue_index")
            index = json.loads(index_data["value"]) if index_data else []
            if item.item_id in index:
                break
            index.append(item.item_id)
            await nosql_set("review_queue_index", json.dumps(index))

            verify_data = await nosql_get("review_queue_index")
            verify_index = json.loads(verify_data["value"]) if verify_data else []
            if item.item_id in verify_index:
                break
        else:
            print(f"[review_queue] Failed to durably index review item "
                  f"{item.item_id!r} after {max_attempts} attempts -- "
                  f"possible concurrent writer contention.")

async def get_pending_review_items(fir_id: str | None = None) -> list[ReviewQueueItem]:
    index_data = await nosql_get("review_queue_index")
    index = json.loads(index_data["value"]) if index_data else []

    # BUG FIX: fetch every indexed item concurrently instead of one at a
    # time. The index only ever grows (see push_review_item -- there's no
    # delete/TTL primitive to prune it), so the old serial
    # "await nosql_get() per item_id" loop turned every GET /api/review-queue
    # call into that many sequential HTTP round-trips to the NoSQL backend
    # (each retryable up to 6x, ~1.5s apart, on transient errors -- see
    # _nosql_request), with total latency scaling with all-time system
    # history rather than what's actually pending. gather() bounds latency to
    # the slowest single call instead of the sum of all of them.
    # NOTE: real pagination and index rotation/pruning are intentionally NOT
    # done here -- both need changes outside this file's scope. The index
    # stores only item_ids (no created_date), so slicing it directly before
    # fetching could return an arbitrary page instead of the newest items
    # (would need index entries to carry sortable metadata, or the route to
    # accept a limit/cursor); pruning reviewed/dismissed ids needs a delete
    # primitive shared/catalyst_client.py doesn't currently expose. Left as
    # follow-up architecture work rather than a half-fix bolted on here.
    raw_items = await asyncio.gather(*(nosql_get(f"review_queue:{item_id}") for item_id in index))

    parsed = []
    for item_id, raw in zip(index, raw_items):
        if not raw:
            continue
        try:
            parsed.append(ReviewQueueItem(**json.loads(raw["value"])))
        except Exception as e:
            # BUG FIX: a single malformed/schema-drifted row (e.g. a future
            # field rename/addition to the model, or a value truncated by a
            # transient write) used to raise uncaught here, 500-ing the whole
            # queue listing for every officer over one bad item. Skip and log
            # the offending item instead of taking down the endpoint.
            print(f"[review_queue] Skipping unparseable review item {item_id!r}: {e}")
            continue

    parsed = [i for i in parsed if i.status == "pending"]
    if fir_id:
        parsed = [i for i in parsed if i.fir_id == fir_id or i.related_fir_id == fir_id]
    
    # Sort newest first
    parsed.sort(key=lambda x: x.created_date, reverse=True)
    return parsed

async def get_review_item(item_id: str) -> ReviewQueueItem | None:
    raw = await nosql_get(f"review_queue:{item_id}")
    if raw:
        # BUG FIX: same unguarded parse as get_pending_review_items -- an
        # unparseable/schema-drifted row used to raise uncaught and 500 the
        # resolve endpoint. Treat it like "not found" (the caller already
        # 404s on None) instead of crashing.
        try:
            return ReviewQueueItem(**json.loads(raw["value"]))
        except Exception as e:
            print(f"[review_queue] Unparseable review item {item_id!r}: {e}")
            return None
    return None
