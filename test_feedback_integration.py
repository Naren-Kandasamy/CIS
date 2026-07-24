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


def test_api_submit_feedback_success():
    print("\n[*] Testing POST /api/feedback/correction (Success Case)...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "event_id": "event-123",
        "session_id": "session-456",
        "officer_id": "dysp1",
        "edge_id": "SHARED_MO_FIR123",
        "edge_type": "SHARED_MO",
        "crime_type": "CSH004",
        "verdict": "confirmed",
        "timestamp": "2026-07-24T10:00:00Z",
        "query_text": "Find associates of Suresh"
    }
    response = client.post("/api/feedback/correction", headers=headers, json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    data = response.json()
    assert data["status"] == "recorded"
    print("  ✅ POST /api/feedback/correction passed!")


def test_api_submit_feedback_invalid_verdict():
    print("\n[*] Testing POST /api/feedback/correction (Invalid Verdict)...")
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "event_id": "event-124",
        "session_id": "session-456",
        "officer_id": "dysp1",
        "edge_id": "SHARED_MO_FIR123",
        "edge_type": "SHARED_MO",
        "crime_type": "CSH004",
        "verdict": "invalid_verdict_value",  # Should trigger validation error
        "timestamp": "2026-07-24T10:00:00Z",
        "query_text": "Find associates of Suresh"
    }
    response = client.post("/api/feedback/correction", headers=headers, json=payload)
    assert response.status_code == 400
    print("  ✅ Invalid verdict validation passed!")


def test_api_submit_feedback_unauthorized():
    print("\n[*] Testing POST /api/feedback/correction (Unauthorized)...")
    payload = {
        "event_id": "event-125",
        "session_id": "session-456",
        "officer_id": "dysp1",
        "edge_id": "SHARED_MO_FIR123",
        "edge_type": "SHARED_MO",
        "crime_type": "CSH004",
        "verdict": "confirmed",
        "timestamp": "2026-07-24T10:00:00Z",
        "query_text": "Find associates of Suresh"
    }
    response = client.post("/api/feedback/correction", json=payload)
    assert response.status_code == 401
    print("  ✅ Unauthorized feedback submission rejected successfully!")
