import uuid
from datetime import datetime
from shared.exclusion_engine import get_active_exclusions
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item

COLD_CASE_MATCH_THRESHOLD = 0.75   # reuse whatever similarity scale SHARED_MO already uses

async def run_cold_case_match(new_fir, shared_mo_matches: list[dict]):
    """
    Called right after the incremental SHARED_MO computation
    for a newly ingested FIR. `shared_mo_matches` is whatever that existing step already
    computed -- this function does NOT recompute matching, it filters
    and routes the existing output.
    """
    for match in shared_mo_matches:
        # Check if the matched FIR has exhausted all leads (is_cold = True)
        # Using .get() defensively depending on how the match dict is structured
        if not match.get("is_cold", False):
            continue
            
        if match.get("score", 0.0) < COLD_CASE_MATCH_THRESHOLD:
            continue

        exclusions = await get_active_exclusions(match.get("matched_fir_id"))
        if match.get("accused_id") in exclusions:
            continue  # already ruled out for that case -- don't proactively re-surface it

        item = ReviewQueueItem(
            item_id=str(uuid.uuid4()),
            item_type="cold_case_match",
            fir_id=new_fir.get("fir_internal_id") if isinstance(new_fir, dict) else new_fir.fir_internal_id,
            related_fir_id=match.get("matched_fir_id"),
            accused_id=match.get("accused_id"),
            summary=(f"New FIR {new_fir.get('crime_no') if isinstance(new_fir, dict) else getattr(new_fir, 'crime_no', 'unknown')} "
                     f"shares MO similarity ({match.get('score', 0):.0%}) with cold case "
                     f"{match.get('matched_fir_crime_no')}"),
            score=match.get("score", 0.0),
            created_date=datetime.utcnow().isoformat(),
        )
        await push_review_item(item)
