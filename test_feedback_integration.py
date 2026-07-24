"""
Feedback API Integration Tests.
Tests POST /api/feedback/correction end-to-end:
  - valid payload accepted
  - trust weight changes in NoSQL after event
  - invalid/missing fields rejected with 422
  - unauthenticated access rejected with 401
"""
import os
import sys
import asyncio
import uuid
import pytest
from fastapi.testclient import TestClient

os.environ["MOCK_NOSQL_ONLY"] = "true"
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")

def clear_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

async def mock_get_session(token: str):
    if token == "mock-valid-token":
        return {"username": "officer1", "role": "si", "display_name": "SI Kumar"}
    return None

import shared.auth
shared.auth.get_session = mock_get_session

import backend.api.middleware.rbac
backend.api.middleware.rbac.get_session = mock_get_session

from backend.main import app
client = TestClient(app)

AUTH = {"Authorization": "Bearer mock-valid-token"}

def _valid_payload(**overrides) -> dict:
    base = {
        "event_id": str(uuid.uuid4()),
        "session_id": str(uuid.uuid4()),
        "officer_id": "officer1",
        "timestamp": "2026-07-24T12:00:00Z",
        "query_text": "Are any cases linked to Ravi Shankar?",
        "edge_type": "SHARED_MO",
        "crime_type": None,
        "edge_id": f"SHARED_MO_{uuid.uuid4().hex[:8]}",
        "verdict": "corrected",
        "explanation": "This link does not apply to this district."
    }
    base.update(overrides)
    return base


def test_feedback_correction_accepted():
    """POST /api/feedback/correction with valid payload must return 200."""
    print("\n[*] Testing POST /api/feedback/correction (valid payload)...")
    clear_mock_db()

    response = client.post("/api/feedback/correction", headers=AUTH, json=_valid_payload())
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text}"
    )
    data = response.json()
    assert data.get("status") == "recorded", (
        f"Expected status='recorded', got: {data}"
    )
    print("  ✅ Valid correction payload accepted (200 / recorded)!")


def test_feedback_correction_confirmed_verdict():
    """POST /api/feedback/correction with verdict='confirmed' must also return 200."""
    print("\n[*] Testing POST /api/feedback/correction (confirmed verdict)...")
    clear_mock_db()

    payload = _valid_payload(verdict="confirmed", explanation=None)
    response = client.post("/api/feedback/correction", headers=AUTH, json=payload)
    assert response.status_code == 200, (
        f"Expected 200 for 'confirmed' verdict, got {response.status_code}. Body: {response.text}"
    )
    print("  ✅ Confirmed verdict accepted!")


def test_feedback_trust_weight_changes_after_correction():
    """After recording a correction event, the trust weight for that edge_type must decrease."""
    print("\n[*] Testing trust weight decreases after feedback correction...")
    clear_mock_db()

    from shared.feedback_engine import get_trust_weight

    # Baseline trust weight before any feedback
    baseline = asyncio.run(get_trust_weight("SHARED_MO", None))
    assert abs(baseline - 0.7) < 1e-5, f"Expected baseline 0.7, got {baseline}"

    # Post one correction
    payload = _valid_payload(edge_type="SHARED_MO", crime_type=None, verdict="corrected")
    response = client.post("/api/feedback/correction", headers=AUTH, json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Trust weight must have dropped below baseline
    new_weight = asyncio.run(get_trust_weight("SHARED_MO", None))
    assert new_weight < baseline, (
        f"Trust weight must decrease after correction: baseline={baseline}, new={new_weight}"
    )
    assert new_weight > 0.3, f"Trust weight must not fall below floor 0.3: got {new_weight}"
    print(f"  Trust weight changed: {baseline:.4f} → {new_weight:.4f}")
    print("  ✅ Trust weight decreases after feedback correction!")


def test_feedback_correction_unauthenticated():
    """POST /api/feedback/correction without auth must return 401."""
    print("\n[*] Testing POST /api/feedback/correction (no auth)...")
    response = client.post("/api/feedback/correction", json=_valid_payload())
    assert response.status_code == 401, (
        f"Expected 401 for missing auth, got {response.status_code}"
    )
    response2 = client.post(
        "/api/feedback/correction",
        headers={"Authorization": "Bearer bad-token"},
        json=_valid_payload()
    )
    assert response2.status_code == 401, (
        f"Expected 401 for invalid token, got {response2.status_code}"
    )
    print("  ✅ Unauthenticated access rejected (401)!")


def test_feedback_correction_missing_required_fields():
    """POST /api/feedback/correction missing required fields must return 422."""
    print("\n[*] Testing POST /api/feedback/correction (missing fields)...")

    # Missing verdict
    payload = _valid_payload()
    del payload["verdict"]
    response = client.post("/api/feedback/correction", headers=AUTH, json=payload)
    assert response.status_code == 422, (
        f"Expected 422 for missing 'verdict', got {response.status_code}. Body: {response.text}"
    )

    # Missing event_id
    payload2 = _valid_payload()
    del payload2["event_id"]
    response2 = client.post("/api/feedback/correction", headers=AUTH, json=payload2)
    assert response2.status_code == 422, (
        f"Expected 422 for missing 'event_id', got {response2.status_code}"
    )

    # Missing session_id
    payload3 = _valid_payload()
    del payload3["session_id"]
    response3 = client.post("/api/feedback/correction", headers=AUTH, json=payload3)
    assert response3.status_code == 422, (
        f"Expected 422 for missing 'session_id', got {response3.status_code}"
    )
    print("  ✅ Missing required fields rejected (422)!")


def test_feedback_correction_invalid_verdict():
    """POST /api/feedback/correction with an invalid verdict value must return 400.
    
    The feedback route validates verdict manually (not via Pydantic Literal), so
    the response is 400 (not 422). This is the established API contract.
    """
    print("\n[*] Testing POST /api/feedback/correction (invalid verdict)...")
    payload = _valid_payload(verdict="maybe")
    response = client.post("/api/feedback/correction", headers=AUTH, json=payload)
    assert response.status_code == 400, (
        f"Expected 400 for invalid verdict 'maybe', got {response.status_code}. Body: {response.text}"
    )
    print("  ✅ Invalid verdict rejected (400)!")


if __name__ == "__main__":
    test_feedback_correction_accepted()
    test_feedback_correction_confirmed_verdict()
    test_feedback_trust_weight_changes_after_correction()
    test_feedback_correction_unauthenticated()
    test_feedback_correction_missing_required_fields()
    test_feedback_correction_invalid_verdict()
    print("\n🎉 ALL FEEDBACK INTEGRATION TESTS PASSED!")
