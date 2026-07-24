import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.hypothesis_models import HypothesisRecord, HypothesisCheckLog
from shared.hypothesis_engine import (
    create_hypothesis,
    get_hypothesis,
    list_hypotheses,
    check_hypothesis,
    resolve_hypothesis,
)


@pytest.mark.asyncio
async def test_create_and_list_hypothesis():
    print("\n[*] Testing Hypothesis Creation and Retrieval...")
    fir_id = "FIR-HYP-TEST-001"
    record = HypothesisRecord(
        hypothesis_id="hyp-001",
        fir_id=fir_id,
        officer_id="dysp1",
        statement="Suspect A and Suspect B used a shared vehicle registered in Hubballi",
        linked_entity_ids=["ACC_001", "ACC_002"],
        status="open",
        created_date="2026-07-21T20:00:00Z",
    )

    await create_hypothesis(record)

    fetched = await get_hypothesis("hyp-001")
    assert fetched is not None
    assert fetched.statement == record.statement
    assert fetched.linked_entity_ids == ["ACC_001", "ACC_002"]
    assert fetched.status == "open"

    case_list = await list_hypotheses(fir_id)
    assert len(case_list) >= 1
    assert any(h.hypothesis_id == "hyp-001" for h in case_list)
    print("  ✅ Hypothesis creation and listing passed!")


@pytest.mark.asyncio
async def test_check_hypothesis():
    print("\n[*] Testing Hypothesis Evidence Check...")
    fir_id = "FIR-HYP-TEST-002"
    record = HypothesisRecord(
        hypothesis_id="hyp-002",
        fir_id=fir_id,
        officer_id="inspector1",
        statement="Jewelry shop heist was executed using a specialized glass cutter",
        linked_entity_ids=["FIR_999", "ACC_005"],
        status="open",
        created_date="2026-07-21T21:00:00Z",
    )
    await create_hypothesis(record)

    log = await check_hypothesis("hyp-002")
    assert isinstance(log, HypothesisCheckLog), (
        f"Expected HypothesisCheckLog, got {type(log)}"
    )
    assert log.hypothesis_id == "hyp-002", (
        f"Expected hypothesis_id='hyp-002', got '{log.hypothesis_id}'"
    )
    # Strict: counts must be non-negative integers (not floats or None)
    assert isinstance(log.new_supporting_evidence_count, int), (
        f"Expected int for new_supporting_evidence_count, got {type(log.new_supporting_evidence_count)}"
    )
    assert isinstance(log.new_contradicting_evidence_count, int), (
        f"Expected int for new_contradicting_evidence_count, got {type(log.new_contradicting_evidence_count)}"
    )
    assert log.new_supporting_evidence_count >= 0, "Supporting count must be non-negative"
    assert log.new_contradicting_evidence_count >= 0, "Contradicting count must be non-negative"
    # Strict: notes must be a non-empty string describing the result
    assert isinstance(log.notes, str) and len(log.notes) > 0, (
        f"Expected non-empty string for notes, got: {log.notes!r}"
    )
    # Strict: the notes must describe the evidence counts found (format contract)
    assert "new supporting item" in log.notes or "No new evidence" in log.notes, (
        f"Notes must describe evidence result, got: {log.notes!r}"
    )
    print("  ✅ Hypothesis evidence check passed!")


@pytest.mark.asyncio
async def test_resolve_hypothesis():
    print("\n[*] Testing Hypothesis Resolution...")
    fir_id = "FIR-HYP-TEST-003"
    record = HypothesisRecord(
        hypothesis_id="hyp-003",
        fir_id=fir_id,
        officer_id="si1",
        statement="Alibi confirmed via cell tower logs at time of incident",
        linked_entity_ids=["ACC_010"],
        status="open",
        created_date="2026-07-21T22:00:00Z",
    )
    await create_hypothesis(record)

    # Invalid status should fail
    with pytest.raises(ValueError):
        await resolve_hypothesis("hyp-003", "invalid_status", "si1", "reason")

    # Confirm hypothesis
    resolved = await resolve_hypothesis("hyp-003", "confirmed", "si1", "Tower logs match alibi location")
    assert resolved.status == "confirmed"
    assert resolved.resolved_by == "si1"
    assert resolved.resolved_reason == "Tower logs match alibi location"
    assert resolved.resolved_date is not None

    # Verify state updated in DB
    refetched = await get_hypothesis("hyp-003")
    assert refetched.status == "confirmed"
    print("  ✅ Hypothesis resolution passed!")


async def main():
    print("==========================================")
    print("Running Hypothesis Workspace Unit Tests...")
    print("==========================================")
    await test_create_and_list_hypothesis()
    await test_check_hypothesis()
    await test_resolve_hypothesis()
    print("\n🎉 ALL HYPOTHESIS TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
