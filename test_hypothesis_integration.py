import os
import sys
import pytest
from fastapi.testclient import TestClient

# Mock NoSQL
os.environ["MOCK_NOSQL_ONLY"] = "true"

# Ensure imports work from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

async def mock_get_session(token: str):
    if token == "mock-valid-token":
        return {
            "username": "dysp1",
            "role": "dysp",
            "display_name": "DySP Rao"
        }
    return None

import shared.auth
shared.auth.get_session = mock_get_session

import backend.api.middleware.rbac
backend.api.middleware.rbac.get_session = mock_get_session

from backend.main import app
client = TestClient(app)


def test_api_create_hypothesis_success():
    print("\n[*] Testing POST /api/investigation/hypothesis (Success Case)...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "fir_id": "FIR_INTEG_001",
        "statement": "The suspect traveled using a stolen motorcycle identified in nearby toll camera data.",
        "linked_entity_ids": ["ACC_TEST_001", "BIKE_PLATE_777"]
    }
    response = client.post("/api/investigation/hypothesis", headers=headers, json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    data = response.json()
    assert data["status"] == "created"
    assert data["hypothesis"]["statement"] == payload["statement"]
    assert data["hypothesis"]["fir_id"] == "FIR_INTEG_001"
    print("  ✅ POST /api/investigation/hypothesis passed!")


def test_api_create_hypothesis_unauthorized():
    print("\n[*] Testing POST /api/investigation/hypothesis (Unauthorized)...")
    # Empty or missing auth header
    response = client.post("/api/investigation/hypothesis", json={"fir_id": "FIR_1", "statement": "test"})
    assert response.status_code == 401
    
    # Invalid token
    headers = {"Authorization": "Bearer invalid-token"}
    response = client.post("/api/investigation/hypothesis", headers=headers, json={"fir_id": "FIR_1", "statement": "test"})
    assert response.status_code == 401
    print("  ✅ POST /api/investigation/hypothesis validation passed!")


def test_api_list_hypotheses():
    print("\n[*] Testing GET /api/investigation/hypothesis/{fir_id}...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    # Create one first
    payload = {
        "fir_id": "FIR_INTEG_LIST_001",
        "statement": "Another investigative theory statement.",
        "linked_entity_ids": []
    }
    client.post("/api/investigation/hypothesis", headers=headers, json=payload)

    response = client.get("/api/investigation/hypothesis/FIR_INTEG_LIST_001", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["fir_id"] == "FIR_INTEG_LIST_001"
    assert len(data["hypotheses"]) >= 1
    assert data["hypotheses"][0]["statement"] == payload["statement"]
    print("  ✅ GET /api/investigation/hypothesis/{fir_id} passed!")


def test_api_check_hypothesis():
    print("\n[*] Testing POST /api/investigation/hypothesis/{id}/check...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    # Create one first
    create_res = client.post("/api/investigation/hypothesis", headers=headers, json={
        "fir_id": "FIR_INTEG_CHECK",
        "statement": "Checking this theory",
        "linked_entity_ids": ["ACC_CHECK"]
    })
    hyp_id = create_res.json()["hypothesis"]["hypothesis_id"]

    # Run check
    response = client.post(f"/api/investigation/hypothesis/{hyp_id}/check", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "checked"
    assert "log" in data
    assert data["log"]["hypothesis_id"] == hyp_id
    print("  ✅ POST /api/investigation/hypothesis/{id}/check passed!")


def test_api_resolve_hypothesis():
    print("\n[*] Testing POST /api/investigation/hypothesis/{id}/resolve...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    # Create one first
    create_res = client.post("/api/investigation/hypothesis", headers=headers, json={
        "fir_id": "FIR_INTEG_RESOLVE",
        "statement": "Theory to resolve",
        "linked_entity_ids": []
    })
    hyp_id = create_res.json()["hypothesis"]["hypothesis_id"]

    # Try resolving with invalid status
    bad_payload = {"status": "invalid_status", "resolved_reason": "none"}
    response = client.post(f"/api/investigation/hypothesis/{hyp_id}/resolve", headers=headers, json=bad_payload)
    assert response.status_code == 400

    # Resolve successfully
    ok_payload = {"status": "confirmed", "resolved_reason": "Alibi was validated by multiple witnesses"}
    response = client.post(f"/api/investigation/hypothesis/{hyp_id}/resolve", headers=headers, json=ok_payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "resolved"
    assert data["hypothesis"]["status"] == "confirmed"
    assert data["hypothesis"]["resolved_reason"] == ok_payload["resolved_reason"]
    print("  ✅ POST /api/investigation/hypothesis/{id}/resolve passed!")
