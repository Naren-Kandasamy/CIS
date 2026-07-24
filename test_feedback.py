import asyncio
import os
import sys
import json
import shutil
import uuid

# Ensure the script can import shared and pipeline_function modules
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
os.environ["MOCK_NOSQL_ONLY"] = "true"

from shared.feedback_models import CorrectionEvent
from shared.feedback_engine import get_trust_weight, record_feedback_event
from pipeline_function.pipeline.evidence import EvidenceItem, EvidenceObject
from pipeline_function.pipeline.retrieval.executor import apply_trust_weighting
from pipeline_function.pipeline.confidence_engine import run_confidence_engine, compute_confidence

# Helper to clear mock NoSQL database between test scenarios
MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")

def clear_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

async def test_neutral_prior():
    print("[*] Scenario 1: Verify neutral starting trust (0.7)")
    clear_mock_db()
    
    # 0 observations
    weight = await get_trust_weight("SHARED_MO", None)
    print(f"    SHARED_MO weight: {weight}")
    assert abs(weight - 0.7) < 1e-5, f"Expected 0.7, got {weight}"
    print("    ✅ Neutral prior verification passed!")

async def test_progressive_feedback():
    print("[*] Scenario 2: Verify progressive trust score changes (damped drop)")
    clear_mock_db()
    
    # 1 correction event (downvote)
    event = CorrectionEvent(
        event_id=str(uuid.uuid4()),
        session_id="session-1",
        officer_id="officer-1",
        timestamp="2026-07-16T12:00:00Z",
        query_text="Test query",
        edge_type="SHARED_MO",
        crime_type="CSH004",
        edge_id="SHARED_MO_FIR123",
        verdict="corrected",
        explanation="Incorrect connection"
    )
    
    await record_feedback_event(event)
    
    # Broad scope trust weight should drop moderately (to ~0.636)
    broad_weight = await get_trust_weight("SHARED_MO", None)
    print(f"    Broad SHARED_MO weight after 1 correction: {broad_weight}")
    assert broad_weight < 0.7, "Expected weight to drop below 0.7"
    assert abs(broad_weight - 0.636) < 0.01, f"Expected ~0.636, got {broad_weight}"
    
    # Narrow scope does not have enough samples (1 < 15), so it should fallback to broad scope (which is ~0.636)
    narrow_weight = await get_trust_weight("SHARED_MO", "CSH004")
    print(f"    Narrow SHARED_MO::CSH004 weight (under sample limit): {narrow_weight}")
    assert abs(narrow_weight - broad_weight) < 1e-5, "Expected fallback to broad scope weight"
    
    # Verify narrow scope when samples >= 15
    # Let's seed 15 corrections in CSH004
    for _ in range(14):
        await record_feedback_event(CorrectionEvent(
            event_id=str(uuid.uuid4()),
            session_id="session-1",
            officer_id="officer-1",
            timestamp="2026-07-16T12:00:00Z",
            query_text="Test query",
            edge_type="SHARED_MO",
            crime_type="CSH004",
            edge_id="SHARED_MO_FIR123",
            verdict="corrected"
        ))
    
    narrow_weight_active = await get_trust_weight("SHARED_MO", "CSH004")
    print(f"    Narrow SHARED_MO::CSH004 weight (15 corrections): {narrow_weight_active}")
    assert narrow_weight_active < 0.4, "Expected narrow scope to drop heavily"
    print("    ✅ Progressive feedback and narrow-then-broad fallback passed!")

async def test_clamping_floor():
    print("[*] Scenario 3: Verify trust score is clamped at floor (0.3)")
    clear_mock_db()
    
    # Record 100 corrections to push score down
    for _ in range(100):
        await record_feedback_event(CorrectionEvent(
            event_id=str(uuid.uuid4()),
            session_id="session-1",
            officer_id="officer-1",
            timestamp="2026-07-16T12:00:00Z",
            query_text="Test query",
            edge_type="SHARED_MO",
            crime_type=None,
            edge_id="SHARED_MO_FIR123",
            verdict="corrected"
        ))
        
    weight = await get_trust_weight("SHARED_MO", None)
    print(f"    Weight after 100 corrections: {weight}")
    assert abs(weight - 0.3) < 1e-5, f"Expected clamped to floor 0.3, got {weight}"
    print("    ✅ Clamping floor verification passed!")

async def test_same_session_penalty():
    print("[*] Scenario 4: Verify same-session penalty and recovery in different session")
    clear_mock_db()
    
    # 1 correction in session-A
    event = CorrectionEvent(
        event_id=str(uuid.uuid4()),
        session_id="session-A",
        officer_id="officer-1",
        timestamp="2026-07-16T12:00:00Z",
        query_text="Test query",
        edge_type="SHARED_MO",
        crime_type="CSH004",
        edge_id="SHARED_MO_FIR123",
        verdict="corrected"
    )
    await record_feedback_event(event)
    
    # Create evidence object
    evidence = EvidenceObject(
        query="Test query",
        session_id="session-A",
        urgency="analytical",
        intent="lookup",
        entities={}
    )
    evidence.items.append(EvidenceItem(
        fir_id="FIR123",
        relevance_score=1.0,
        sources=["graph"],
        convergent=False,
        evidence_path="SHARED_MO via FIR123",
        similarity_reason=None,
        edge_type="SHARED_MO",
        edge_id="SHARED_MO_FIR123",
        crime_type="CSH004"
    ))
    
    # Apply trust weighting for session-A
    await apply_trust_weighting(evidence, "session-A")
    score_session_a = evidence.items[0].relevance_score
    print(f"    Relevance score in session-A (penalized): {score_session_a}")
    
    # Recovery check: Apply trust weighting for session-B
    evidence_b = EvidenceObject(
        query="Test query",
        session_id="session-B",
        urgency="analytical",
        intent="lookup",
        entities={}
    )
    evidence_b.items.append(EvidenceItem(
        fir_id="FIR123",
        relevance_score=1.0,
        sources=["graph"],
        convergent=False,
        evidence_path="SHARED_MO via FIR123",
        similarity_reason=None,
        edge_type="SHARED_MO",
        edge_id="SHARED_MO_FIR123",
        crime_type="CSH004"
    ))
    
    await apply_trust_weighting(evidence_b, "session-B")
    score_session_b = evidence_b.items[0].relevance_score
    print(f"    Relevance score in session-B (normal): {score_session_b}")
    
    # session B should be normal (broad score, around 0.636), session A should be 0.5x that (~0.318)
    assert abs(score_session_b - 0.636) < 0.01, f"Expected normal score ~0.636, got {score_session_b}"
    assert abs(score_session_a - 0.318) < 0.01, f"Expected penalized score ~0.318, got {score_session_a}"
    print("    ✅ Same-session penalty and recovery verification passed!")

async def test_confidence_engine():
    print("[*] Scenario 5: Verify confidence engine folds in trust weights")
    clear_mock_db()
    
    # Seed 10 corrections on SHARED_MO to drop trust weight to 0.35
    for _ in range(10):
        await record_feedback_event(CorrectionEvent(
            event_id=str(uuid.uuid4()),
            session_id="session-A",
            officer_id="officer-1",
            timestamp="2026-07-16T12:00:00Z",
            query_text="Test query",
            edge_type="SHARED_MO",
            crime_type=None,
            edge_id="SHARED_MO_FIR123",
            verdict="corrected"
        ))
    
    # Create evidence object
    evidence = EvidenceObject(
        query="Test query",
        session_id="session-A",
        urgency="analytical",
        intent="lookup",
        entities={}
    )
    evidence.items.append(EvidenceItem(
        fir_id="FIR123",
        relevance_score=0.9,
        sources=["graph"],
        convergent=False,
        evidence_path="SHARED_MO via FIR123",
        similarity_reason=None,
        edge_type="SHARED_MO",
        edge_id="SHARED_MO_FIR123",
        crime_type=None
    ))
    
    # Run confidence engine
    await run_confidence_engine(evidence)
    score_with_trust = evidence.items[0].relevance_score
    print(f"    Relevance score after confidence engine: {score_with_trust}")
    
    # Normal base final would be (0.75 * 0.45) + (0.75 * 0.40) + (0.5 * 0.15) = 0.3375 + 0.3 + 0.075 = 0.7125
    # Trust weight after 10 corrections is (0 + 7) / (10 + 10) = 7/20 = 0.35
    # So final confidence score should be 0.7125 * 0.35 = 0.249
    assert abs(score_with_trust - 0.249) < 0.01, f"Expected score around 0.249, got {score_with_trust}"
    print("    ✅ Confidence engine integration passed!")

async def main():
    try:
        await test_neutral_prior()
        await test_progressive_feedback()
        await test_clamping_floor()
        await test_same_session_penalty()
        await test_confidence_engine()
        print("\n🎉 ALL SCENARIOS PASSED SUCCESSFULLY!")
    finally:
        clear_mock_db()

if __name__ == "__main__":
    asyncio.run(main())
