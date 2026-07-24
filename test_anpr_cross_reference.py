"""
ANPR & Wanted Vehicle Cross-Referencing Unit and Integration Tests.
Tests:
  1. ANPRProvider plate read generation with authentic Indian registration formats & source_provenance.
  2. Ingesting clean vehicle plates writes ANPR_HIT edges without pushing alerts.
  3. Ingesting wanted vehicle plates produces anpr_wanted_hit ReviewQueueItem alert in NoSQL store.
"""
import os
import sys
import asyncio
import pytest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.data_sources.synthetic_anpr import SyntheticANPRProvider
from shared.anpr_models import WantedVehicleRecord
from shared.anpr_engine import register_wanted_vehicle, get_wanted_vehicle
from ingestion.anpr_ingest import ingest_and_check_anpr
from shared.review_queue_engine import get_pending_review_items

MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")

def clear_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

@pytest.mark.asyncio
async def test_synthetic_anpr_provider():
    print("\n[*] Testing SyntheticANPRProvider...")
    provider = SyntheticANPRProvider(seed=123)
    start = datetime.now(timezone.utc) - timedelta(days=1)
    end = datetime.now(timezone.utc)
    
    reads = await provider.fetch_plate_reads("KA 04 MB 8819", start, end)
    assert len(reads) > 0, "Expected at least 1 plate read event"
    for r in reads:
        assert r["plate_number"] == "KA 04 MB 8819"
        assert "CAM-BGLR-" in r["camera_id"]
        assert 12.0 < r["lat"] < 13.5, f"Latitude out of Bengaluru bounding box: {r['lat']}"
        assert 77.0 < r["lon"] < 78.5, f"Longitude out of Bengaluru bounding box: {r['lon']}"
        assert r["source_provenance"] == "synthetic_demo", "Must contain source_provenance='synthetic_demo'"
    print("  ✅ SyntheticANPRProvider test passed!")

@pytest.mark.asyncio
async def test_wanted_vehicle_registry():
    print("\n[*] Testing Wanted Vehicle Registry persistence...")
    clear_mock_db()
    
    rec = WantedVehicleRecord(
        plate_number="KA 04 MB 8819",
        reason="stolen",
        fir_id="FIR-2026-BGLR-099",
        flagged_date=datetime.now(timezone.utc).isoformat()
    )
    await register_wanted_vehicle(rec)
    
    fetched = await get_wanted_vehicle("KA 04 MB 8819")
    assert fetched is not None, "Failed to retrieve wanted vehicle record"
    assert fetched.plate_number == "KA 04 MB 8819"
    assert fetched.reason == "stolen"
    assert fetched.fir_id == "FIR-2026-BGLR-099"
    print("  ✅ Wanted Vehicle Registry persistence passed!")

@pytest.mark.asyncio
async def test_anpr_ingest_clean_vehicle():
    print("\n[*] Testing ANPR Ingest (Clean / Unwanted Vehicle)...")
    clear_mock_db()
    
    start = datetime.now(timezone.utc) - timedelta(hours=2)
    end = datetime.now(timezone.utc)
    
    # Ingest plate that is NOT in wanted registry
    alert = await ingest_and_check_anpr("MH 12 CD 5678", start, end)
    assert alert is None, "Clean vehicle must NOT produce an alert"
    
    pending = await get_pending_review_items()
    assert len(pending) == 0, f"Expected 0 pending alerts, got {len(pending)}"
    print("  ✅ Clean vehicle ingestion passed!")

@pytest.mark.asyncio
async def test_anpr_ingest_wanted_vehicle():
    print("\n[*] Testing ANPR Ingest (Wanted Vehicle Hit)...")
    clear_mock_db()
    
    # 1. Register vehicle as wanted
    wanted_rec = WantedVehicleRecord(
        plate_number="TN 38 BY 1204",
        reason="linked_to_open_case",
        fir_id="FIR-2026-COLD-55",
        flagged_date=datetime.now(timezone.utc).isoformat()
    )
    await register_wanted_vehicle(wanted_rec)
    
    start = datetime.now(timezone.utc) - timedelta(hours=5)
    end = datetime.now(timezone.utc)
    
    # 2. Ingest camera plate reads for the wanted vehicle
    alert = await ingest_and_check_anpr("TN 38 BY 1204", start, end)
    assert alert is not None, "Wanted vehicle hit MUST produce a ReviewQueueItem alert"
    assert alert.item_type == "anpr_wanted_hit", f"Expected item_type='anpr_wanted_hit', got '{alert.item_type}'"
    assert alert.fir_id == "FIR-2026-COLD-55"
    assert "TN 38 BY 1204" in alert.summary
    assert "linked_to_open_case" in alert.summary
    
    # 3. Verify alert appears in Review Queue
    pending = await get_pending_review_items()
    assert len(pending) == 1, f"Expected 1 pending alert in review queue, got {len(pending)}"
    assert pending[0].item_id == alert.item_id
    assert pending[0].item_type == "anpr_wanted_hit"
    print("  ✅ Wanted vehicle ANPR hit alert generation passed!")

async def main():
    print("==========================================")
    print("Running ANPR Cross-Referencing Unit Tests...")
    print("==========================================")
    await test_synthetic_anpr_provider()
    await test_wanted_vehicle_registry()
    await test_anpr_ingest_clean_vehicle()
    await test_anpr_ingest_wanted_vehicle()
    print("\n🎉 ALL ANPR CROSS-REFERENCING TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    asyncio.run(main())
