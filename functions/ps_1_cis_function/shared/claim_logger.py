import uuid
import json
from datetime import datetime
from shared.claim_models import ClaimRecord
from shared.catalyst_client import nosql_get, nosql_set, get_lock
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item

# TTL set for 30 days (in seconds) to prevent table bloat
CLAIM_TTL = 30 * 24 * 60 * 60

async def log_claim(fir_id: str, accused_id: str | None, evidence_ref: str | None, 
                   confidence_tier: str, snippet: str):
    """
    Logs a HIGH/MEDIUM confidence claim to NoSQL, indexed by FIR_ID for O(1) retrieval.
    """
    if confidence_tier not in {"HIGH", "MEDIUM"}:
        return  # LOW-confidence claims aren't worth tracking for contradiction alerts
        
    record = ClaimRecord(
        claim_id=str(uuid.uuid4()),
        fir_id=fir_id,
        accused_id=accused_id,
        evidence_ref=evidence_ref,
        confidence_tier=confidence_tier,
        synthesized_snippet=snippet,
        timestamp=datetime.utcnow().isoformat()
    )
    
    # Save the actual claim with TTL
    await nosql_set(f"claim:{record.claim_id}", record.model_dump_json(), ttl=CLAIM_TTL)

    # Update the FIR index for O(1) lookup later
    # BUG FIX: this read-modify-write ran completely unlocked -- concurrent
    # queries touching the same FIR (multiple officers, or overlapping
    # pipeline runs) could both read the same stale index snapshot, and the
    # later write would silently drop the earlier one's claim_id. That claim
    # would still exist at claim:{id} but never be found by
    # check_and_flag_contradicted_claims's index lookup, silently defeating
    # the contradiction-detection feature for that claim. Same bug class
    # already fixed for hypothesis_engine.py's/review_queue_engine.py's index
    # writes; guarded with the existing per-key lock registry here.
    index_key = f"claim_index:{fir_id}"
    async with get_lock(index_key):
        index_data = await nosql_get(index_key)
        index = json.loads(index_data["value"]) if index_data else []

        if record.claim_id not in index:
            index.append(record.claim_id)
            await nosql_set(index_key, json.dumps(index), ttl=CLAIM_TTL)

async def check_and_flag_contradicted_claims(fir_id: str, accused_id: str | None, reason: str):
    """
    Checks if a newly logged exclusion contradicts any past LLM claims.
    Uses O(1) index lookup by FIR_ID to avoid full table scans.
    """
    index_key = f"claim_index:{fir_id}"
    index_data = await nosql_get(index_key)
    
    if not index_data:
        return # No past claims for this FIR, exit quickly.
        
    claim_ids = json.loads(index_data["value"])
    
    for claim_id in claim_ids:
        raw = await nosql_get(f"claim:{claim_id}")
        if not raw:
            continue
            
        claim = ClaimRecord(**json.loads(raw["value"]))
        
        # Skip if already contradicted or doesn't match the accused
        if claim.contradicted:
            continue
        if accused_id and claim.accused_id != accused_id:
            continue
            
        # We found a contradiction!
        claim.contradicted = True
        claim.contradicted_date = datetime.utcnow().isoformat()
        
        # Update claim (keep existing TTL by omitting ttl param or passing original)
        await nosql_set(f"claim:{claim.claim_id}", claim.model_dump_json())
        
        # Push to review queue
        alert = ReviewQueueItem(
            item_id=str(uuid.uuid4()), 
            item_type="contradiction_alert",
            fir_id=fir_id, 
            accused_id=accused_id,
            summary=(f"Earlier analysis rated a connection as {claim.confidence_tier} "
                     f"confidence (\"{claim.synthesized_snippet}\"); this has since "
                     f"been contradicted: {reason}. Recommend reviewing any decisions "
                     f"made based on that assessment."),
            created_date=datetime.utcnow().isoformat()
        )
        await push_review_item(alert)
