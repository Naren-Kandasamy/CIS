import os
import sys
import pytest
import json
from fastapi.testclient import TestClient

# Mock NoSQL
os.environ["MOCK_NOSQL_ONLY"] = "true"

# Ensure imports work from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

# Define mocks
async def mock_get_session(token: str):
    if token == "mock-valid-token":
        return {
            "username": "dysp1",
            "role": "dysp",
            "display_name": "DySP Rao"
        }
    return None

async def mock_get_user(username: str):
    # Mock return values for get_user validation
    if username in {"dysp1", "inspector1", "si1"}:
        return {
            "username": username,
            "role": "inspector",
            "display_name": "Valid Officer"
        }
    return None

import shared.auth
shared.auth.get_session = mock_get_session
shared.auth.get_user = mock_get_user

import backend.api.middleware.rbac
backend.api.middleware.rbac.get_session = mock_get_session

import backend.api.routes.cases
backend.api.routes.cases.get_user = mock_get_user

from backend.main import app
client = TestClient(app)

# Helper to create a case for testing
def _create_mock_case():
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "title": "Case 101: Robbery at MG Road",
        "crime_no": "CRM101",
        "district": "Bengaluru"
    }
    res = client.post("/api/cases", headers=headers, json=payload)
    return res.json()["case_id"]


def test_add_collaborator_validation_success():
    print("\n[*] Testing POST /api/cases/{case_id}/collaborators (Success - Valid Officer)...")
    case_id = _create_mock_case()
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "username": "inspector1"
    }
    response = client.post(f"/api/cases/{case_id}/collaborators", headers=headers, json=payload)
    assert response.status_code == 200, f"Expected 200, got {response.status_code}. Response: {response.text}"
    case_data = response.json()
    assert "inspector1" in case_data["collaborators"]
    print("  ✅ Add collaborator success case passed!")


def test_add_collaborator_validation_not_found():
    print("\n[*] Testing POST /api/cases/{case_id}/collaborators (Failure - Typo'd/Invalid Officer)...")
    case_id = _create_mock_case()
    headers = {"Authorization": "Bearer mock-valid-token"}
    payload = {
        "username": "typod_username_officer"
    }
    response = client.post(f"/api/cases/{case_id}/collaborators", headers=headers, json=payload)
    assert response.status_code == 404, f"Expected 404, got {response.status_code}. Response: {response.text}"
    assert "Officer not found in system" in response.json()["detail"]
    print("  ✅ Add collaborator validation (404 rejection) passed!")
