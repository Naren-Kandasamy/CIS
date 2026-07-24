import asyncio
import os
import sys
import pytest
from datetime import datetime, timezone
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item, get_pending_review_items, resolve_review_item
from shared.catalyst_client import nosql_query_by_prefix
from shared.exclusion_models import ExclusionRecord
from shared.graph_client import close

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
        item_id="alert-001", item_type="cold_case_match",
        fir_id="FIR-NEW-001", related_fir_id="FIR-COLD-001", accused_id="ACC-001",
        summary="MO match alert", score=0.85, created_date=datetime.now(timezone.utc).isoformat()
    )
    item2 = ReviewQueueItem(
        item_id="alert-002", item_type="contradiction_alert",
        fir_id="FIR-NEW-002", summary="Contradiction alert",
        score=0.9, created_date=datetime.now(timezone.utc).isoformat()
    )

    await push_review_item(item1)
    await push_review_item(item2)

    # Strict: prefix query must return exactly 2 items
    raw_items = await nosql_query_by_prefix("review_queue:")
    assert len(raw_items) == 2, f"Expected 2 raw items from prefix scan, got {len(raw_items)}"

    # Both must appear as pending
    pending = await get_pending_review_items()
    assert len(pending) == 2, f"Expected 2 pending items, got {len(pending)}"
    assert any(i.item_id == "alert-001" for i in pending), "alert-001 missing"
    assert any(i.item_id == "alert-002" for i in pending), "alert-002 missing"

    # Strict: filter by FIR ID — exactly 1 result
    filtered = await get_pending_review_items(fir_id="FIR-NEW-001")
    assert len(filtered) == 1, f"Expected 1 filtered item, got {len(filtered)}"
    assert filtered[0].item_id == "alert-001", f"Expected alert-001, got {filtered[0].item_id}"

    # Resolve alert-001
    resolved = await resolve_review_item("alert-001", "reviewed", "dysp1")
    assert resolved is not None, "resolve_review_item returned None"
    assert resolved.status == "reviewed", f"Expected 'reviewed', got '{resolved.status}'"
    assert resolved.reviewed_by == "dysp1", f"Expected 'dysp1', got '{resolved.reviewed_by}'"
    assert resolved.reviewed_date is not None, "reviewed_date must be set"

    # Strict: only alert-002 remains pending
    pending_after = await get_pending_review_items()
    assert len(pending_after) == 1, f"Expected 1 pending after resolve, got {len(pending_after)}"
    assert pending_after[0].item_id == "alert-002"

    # Dismiss is also valid
    resolved2 = await resolve_review_item("alert-002", "dismissed", "inspector1")
    assert resolved2.status == "dismissed"

    # Strict: invalid status must raise ValueError
    try:
        await resolve_review_item("alert-001", "bad_status", "x")
        assert False, "Expected ValueError for invalid status"
    except ValueError:
        pass  # expected

    print("  ✅ Review Queue persistence and queries passed!")


@pytest.mark.asyncio
async def test_cold_case_matcher_filtering():
    print("\n[*] Testing Cold Case Matcher filtering logic...")
    clear_mock_db()

    exclusion = ExclusionRecord(
        exclusion_id="ex-1", fir_id="FIR-COLD-X", accused_id="ACC-EXCLUDED",
        exclusion_type="ruled_out", reason="Has alibi", officer_id="dysp1",
        date=datetime.now(timezone.utc).isoformat()
    )
    mock_exclusions = {"FIR-COLD-X": {"ACC-EXCLUDED": exclusion}}

    async def mock_get_active_exclusions(fir_id: str):
        return mock_exclusions.get(fir_id, {})

    # FIXED: patch() as context manager — scoped strictly to this test.
    # The old `ingestion.cold_case_matcher.get_active_exclusions = fn` was a
    # permanent global mutation that leaked into any test that ran afterward.
    with patch("ingestion.cold_case_matcher.get_active_exclusions", side_effect=mock_get_active_exclusions):
        from ingestion.cold_case_matcher import run_cold_case_match
        new_fir = {"fir_internal_id": "FIR-NEW-M", "crime_no": "Composite-1"}
        matches = [
            # Scenario 1: closed — must be skipped
            {"matched_fir_id": "FIR-CLOSED", "matched_fir_status": "closed",
             "score": 0.9, "accused_id": "ACC-ACTIVE", "matched_fir_crime_no": "CLOSED-NO"},
            # Scenario 2: below threshold — must be skipped
            {"matched_fir_id": "FIR-COLD-Y", "matched_fir_status": "cold",
             "score": 0.65, "accused_id": "ACC-ACTIVE", "matched_fir_crime_no": "COLD-Y-NO"},
            # Scenario 3: excluded accused — must be suppressed
            {"matched_fir_id": "FIR-COLD-X", "matched_fir_status": "open",
             "score": 0.85, "accused_id": "ACC-EXCLUDED", "matched_fir_crime_no": "COLD-X-NO"},
            # Scenario 4: valid — must produce exactly one alert
            {"matched_fir_id": "FIR-COLD-Y", "matched_fir_status": "cold",
             "score": 0.85, "accused_id": "ACC-ACTIVE", "matched_fir_crime_no": "COLD-Y-NO"},
        ]
        await run_cold_case_match(new_fir, matches)

    pending = await get_pending_review_items()
    assert len(pending) == 1, (
        f"Expected exactly 1 alert (Scenario 4 only), got {len(pending)}: "
        f"{[(i.item_id, i.related_fir_id) for i in pending]}"
    )
    assert pending[0].related_fir_id == "FIR-COLD-Y"
    assert pending[0].accused_id == "ACC-ACTIVE"
    assert abs(pending[0].score - 0.85) < 1e-5, f"Score mismatch: {pending[0].score}"
    assert pending[0].fir_id == "FIR-NEW-M"
    assert pending[0].item_type == "cold_case_match"
    print("  ✅ Cold Case Matcher filtering logic passed!")


@pytest.mark.asyncio
async def test_cold_case_matcher_missing_fir_id():
    """Strict: must return early with 0 alerts when fir_internal_id is absent."""
    print("\n[*] Testing Cold Case Matcher with missing fir_internal_id...")
    clear_mock_db()
    from ingestion.cold_case_matcher import run_cold_case_match
    bad_fir = {"crime_no": "NO-ID-FIR"}  # fir_internal_id intentionally absent
    await run_cold_case_match(bad_fir, [
        {"matched_fir_id": "X", "matched_fir_status": "open", "score": 0.9,
         "accused_id": None, "matched_fir_crime_no": "X-1"}
    ])
    pending = await get_pending_review_items()
    assert len(pending) == 0, f"Expected 0 alerts for missing fir_internal_id, got {len(pending)}"
    print("  ✅ Missing fir_internal_id early-return passed!")


@pytest.mark.asyncio
async def test_cold_case_score_threshold_boundary():
    """Strict: score=0.75 must pass; score=0.749 must be rejected."""
    print("\n[*] Testing Cold Case Matcher score threshold boundary...")
    clear_mock_db()

    async def no_exclusions(fir_id: str):
        return {}

    with patch("ingestion.cold_case_matcher.get_active_exclusions", side_effect=no_exclusions):
        from ingestion.cold_case_matcher import run_cold_case_match
        new_fir = {"fir_internal_id": "FIR-THRESH", "crime_no": "THRESH-1"}
        matches = [
            {"matched_fir_id": "FIR-AT",    "matched_fir_status": "open", "score": 0.75,  "accused_id": None, "matched_fir_crime_no": "AT-1"},
            {"matched_fir_id": "FIR-BELOW", "matched_fir_status": "open", "score": 0.749, "accused_id": None, "matched_fir_crime_no": "BELOW-1"},
        ]
        await run_cold_case_match(new_fir, matches)

    pending = await get_pending_review_items()
    assert len(pending) == 1, f"Expected 1 (score=0.75 passes, 0.749 rejected), got {len(pending)}"
    assert pending[0].related_fir_id == "FIR-AT"
    print("  ✅ Score threshold boundary test passed!")


async def main():
    print("==========================================")
    print("Running Cold Case Matcher Unit Tests...")
    print("==========================================")
    await test_review_queue_persistence_and_queries()
    await test_cold_case_matcher_filtering()
    await test_cold_case_matcher_missing_fir_id()
    await test_cold_case_score_threshold_boundary()
    await close()
    print("\n🎉 ALL COLD CASE TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
