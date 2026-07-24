import asyncio
import os
import sys
import pytest
import uuid
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item, get_pending_review_items, resolve_review_item
from shared.catalyst_client import nosql_query_by_prefix
from shared.exclusion_models import ExclusionRecord
from shared.exclusion_engine import create_exclusion
from shared.graph_client import run_write, close
from ingestion.cold_case_matcher import run_cold_case_match

MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")

def clear_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_review_queue_persistence_and_queries():
    print("\n[*] Testing Review Queue persistence and queries...")
    clear_mock_db()
    
    item1 = ReviewQueueItem(
        item_id="alert-001",
        item_type="cold_case_match",
        fir_id="FIR-NEW-001",
        related_fir_id="FIR-COLD-001",
        accused_id="ACC-001",
        summary="MO match alert",
        score=0.85,
        created_date=datetime.now(timezone.utc).isoformat()
    )
    
    item2 = ReviewQueueItem(
        item_id="alert-002",
        item_type="contradiction_alert",
        fir_id="FIR-NEW-002",
        summary="Contradiction alert",
        score=0.9,
        created_date=datetime.now(timezone.utc).isoformat()
    )
    
    await push_review_item(item1)
    await push_review_item(item2)
    
    # Check prefix query
    raw_items = await nosql_query_by_prefix("review_queue:")
    assert len(raw_items) == 2
    
    # Get pending items
    pending = await get_pending_review_items()
    assert len(pending) == 2
    assert any(i.item_id == "alert-001" for i in pending)
    
    # Get pending items filtered by FIR ID
    filtered = await get_pending_review_items(fir_id="FIR-NEW-001")
    assert len(filtered) == 1
    assert filtered[0].item_id == "alert-001"
    
    # Resolve item
    resolved = await resolve_review_item("alert-001", "reviewed", "dysp1")
    assert resolved is not None
    assert resolved.status == "reviewed"
    assert resolved.reviewed_by == "dysp1"
    
    # Verify it is no longer pending
    pending_after = await get_pending_review_items()
    assert len(pending_after) == 1
    assert pending_after[0].item_id == "alert-002"
    print("  ✅ Review Queue persistence and queries passed!")

@pytest.mark.asyncio
async def test_cold_case_matcher_filtering():
    print("\n[*] Testing Cold Case Matcher filtering logic...")
    clear_mock_db()
    
    # Seed an exclusion in the database for ACC-EXCLUDED
    exclusion = ExclusionRecord(
        exclusion_id="ex-1",
        fir_id="FIR-COLD-X",
        accused_id="ACC-EXCLUDED",
        exclusion_type="ruled_out",
        reason="Has alibi",
        officer_id="dysp1",
        date=datetime.now(timezone.utc).isoformat()
    )

    mock_exclusions = {
        "FIR-COLD-X": {"ACC-EXCLUDED": exclusion}
    }

    async def mock_get_active_exclusions(fir_id: str):
        return mock_exclusions.get(fir_id, {})

    import ingestion.cold_case_matcher
    ingestion.cold_case_matcher.get_active_exclusions = mock_get_active_exclusions

    # We will test run_cold_case_match directly with different scenarios
    new_fir = {"fir_internal_id": "FIR-NEW-M", "crime_no": "Composite-1"}
    
    matches = [
        # Scenario 1: Closed case - should be skipped
        {
            "matched_fir_id": "FIR-CLOSED",
            "matched_fir_status": "closed",
            "score": 0.9,
            "accused_id": "ACC-ACTIVE",
            "matched_fir_crime_no": "CLOSED-NO"
        },
        # Scenario 2: Score below threshold (0.75) - should be skipped
        {
            "matched_fir_id": "FIR-COLD-Y",
            "matched_fir_status": "cold",
            "score": 0.65,
            "accused_id": "ACC-ACTIVE",
            "matched_fir_crime_no": "COLD-Y-NO"
        },
        # Scenario 3: Accused has active exclusion - should be suppressed
        {
            "matched_fir_id": "FIR-COLD-X",
            "matched_fir_status": "open",
            "score": 0.85,
            "accused_id": "ACC-EXCLUDED",
            "matched_fir_crime_no": "COLD-X-NO"
        },
        # Scenario 4: Valid match - should generate ReviewQueueItem
        {
            "matched_fir_id": "FIR-COLD-Y",
            "matched_fir_status": "cold",
            "score": 0.85,
            "accused_id": "ACC-ACTIVE",
            "matched_fir_crime_no": "COLD-Y-NO"
        }
    ]
    
    await run_cold_case_match(new_fir, matches)
    
    pending = await get_pending_review_items()
    # Should only contain Scenario 4
    assert len(pending) == 1
    assert pending[0].related_fir_id == "FIR-COLD-Y"
    assert pending[0].accused_id == "ACC-ACTIVE"
    assert pending[0].score == 0.85
    print("  ✅ Cold Case Matcher filtering logic passed!")

async def main():
    print("==========================================")
    print("Running Cold Case Matcher Unit Tests...")
    print("==========================================")
    await test_review_queue_persistence_and_queries()
    await test_cold_case_matcher_filtering()
    await close()
    print("\n🎉 ALL COLD CASE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
