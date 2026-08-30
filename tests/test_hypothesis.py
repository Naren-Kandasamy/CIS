import asyncio
import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.hypothesis_models import HypothesisRecord, HypothesisCheckLog
from shared.hypothesis_engine import (
    create_hypothesis,
    get_hypothesis,
    get_last_check,
    list_hypotheses,
    list_hypotheses_by_case,
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
    assert isinstance(log, HypothesisCheckLog)
    assert log.hypothesis_id == "hyp-002"
    assert log.new_supporting_evidence_count >= 0
    assert log.new_contradicting_evidence_count >= 0
    assert "new supporting item" in log.notes

    # the last check is persisted and readable back (board reload path)
    last = await get_last_check("hyp-002")
    assert isinstance(last, HypothesisCheckLog)
    assert last.check_id == log.check_id
    assert await get_last_check("hyp-never-checked") is None
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


@pytest.mark.asyncio
async def test_case_scoped_hypothesis_indexed_by_case():
    """Phase 4: a hypothesis carrying case_id lands in both the FIR index and
    the hypotheses_by_case:{case_id} index; list_hypotheses_by_case reads it."""
    print("\n[*] Testing case-scoped hypothesis indexing...")
    case_id = "c_hyp_case_001"
    record = HypothesisRecord(
        hypothesis_id="hyp-case-001",
        fir_id=case_id,  # no specific FIR -> route falls back to case_id
        case_id=case_id,
        officer_id="dysp1",
        statement="The 2024 Belagavi thefts share a common accused network",
        linked_entity_ids=["ACC_101", "ACC_102"],
        status="open",
        created_date="2026-08-01T10:00:00Z",
    )
    await create_hypothesis(record)

    by_case = await list_hypotheses_by_case(case_id)
    assert any(h.hypothesis_id == "hyp-case-001" for h in by_case)
    assert all(h.case_id == case_id for h in by_case)

    # still reachable through the FIR index too (fir_id == case_id here)
    by_fir = await list_hypotheses(case_id)
    assert any(h.hypothesis_id == "hyp-case-001" for h in by_fir)
    print("  ✅ case-scoped indexing passed!")


@pytest.mark.asyncio
async def test_legacy_hypothesis_without_case_id_not_in_case_index():
    """A hypothesis with no case_id must not create a hypotheses_by_case:None
    index entry, and an unrelated case must list empty."""
    print("\n[*] Testing legacy (FIR-only) hypothesis stays out of case index...")
    record = HypothesisRecord(
        hypothesis_id="hyp-legacy-001",
        fir_id="FIR-LEGACY-777",
        officer_id="inspector1",
        statement="Legacy hypothesis with no case scope",
        linked_entity_ids=["ACC_900"],
        status="open",
        created_date="2026-08-01T11:00:00Z",
    )
    await create_hypothesis(record)

    assert record.case_id is None
    empty = await list_hypotheses_by_case("c_never_used_999")
    assert empty == []
    print("  ✅ legacy hypothesis isolation passed!")


@pytest.mark.asyncio
async def test_multiple_hypotheses_accumulate_in_one_case_index():
    """Two hypotheses created for the same case_id both survive in the index
    (regression guard for the unlocked read-modify-write bug class)."""
    print("\n[*] Testing case index accumulation...")
    case_id = "c_hyp_case_multi"
    for i in (1, 2, 3):
        await create_hypothesis(HypothesisRecord(
            hypothesis_id=f"hyp-multi-{i}",
            fir_id=case_id,
            case_id=case_id,
            officer_id="dysp1",
            statement=f"Working hypothesis number {i}",
            linked_entity_ids=[f"ACC_{i}0"],
            status="open",
            created_date=f"2026-08-02T0{i}:00:00Z",
        ))

    ids = {h.hypothesis_id for h in await list_hypotheses_by_case(case_id)}
    assert {"hyp-multi-1", "hyp-multi-2", "hyp-multi-3"} <= ids
    print("  ✅ case index accumulation passed!")


async def main():
    print("==========================================")
    print("Running Hypothesis Workspace Unit Tests...")
    print("==========================================")
    await test_create_and_list_hypothesis()
    await test_check_hypothesis()
    await test_resolve_hypothesis()
    await test_case_scoped_hypothesis_indexed_by_case()
    await test_legacy_hypothesis_without_case_id_not_in_case_index()
    await test_multiple_hypotheses_accumulate_in_one_case_index()
    print("\n🎉 ALL HYPOTHESIS TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(main())
