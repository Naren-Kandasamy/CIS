import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from backend.main import app
from shared.exclusion_models import ExclusionRecord
from shared.exclusion_engine import alibi_covers_incident

client = TestClient(app)

def test_alibi_covers_incident_success():
    record = ExclusionRecord(
        exclusion_id="e1",
        fir_id="f1",
        accused_id="a1",
        exclusion_type="alibi_confirmed",
        reason="test",
        time_window_start="2024-01-01T12:00:00",
        time_window_end="2024-01-01T18:00:00",
        officer_id="u1",
        date="2024-01-02T00:00:00"
    )
    assert alibi_covers_incident(record, "2024-01-01T14:00:00") is True

def test_alibi_covers_incident_outside():
    record = ExclusionRecord(
        exclusion_id="e2",
        fir_id="f1",
        accused_id="a1",
        exclusion_type="alibi_confirmed",
        reason="test",
        time_window_start="2024-01-01T12:00:00",
        time_window_end="2024-01-01T18:00:00",
        officer_id="u1",
        date="2024-01-02T00:00:00"
    )
    assert alibi_covers_incident(record, "2024-01-01T19:00:00") is False

def test_ruled_out_always_covers():
    record = ExclusionRecord(
        exclusion_id="e3",
        fir_id="f1",
        accused_id="a1",
        exclusion_type="ruled_out",
        reason="test",
        officer_id="u1",
        date="2024-01-02T00:00:00"
    )
    assert alibi_covers_incident(record, "2024-01-01T19:00:00") is True

def test_api_submit_exclusion_unauthorized():
    payload = {
        "fir_id": "FIR1",
        "accused_id": "ACC1",
        "exclusion_type": "ruled_out",
        "reason": "Not the guy"
    }
    response = client.post("/api/investigation/exclude", json=payload)
    assert response.status_code == 401

@patch("backend.api.middleware.rbac.get_session")
@patch("backend.api.routes.exclusions.create_exclusion")
def test_api_submit_exclusion_authorized(mock_create, mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    
    payload = {
        "fir_id": "FIR1",
        "accused_id": "ACC1",
        "exclusion_type": "ruled_out",
        "reason": "Not the guy"
    }
    response = client.post("/api/investigation/exclude", json=payload, headers={"Authorization": "Bearer mocktoken"})
    
    assert response.status_code == 200
    assert response.json()["status"] == "recorded"
    assert "exclusion_id" in response.json()
    mock_create.assert_called_once()

@patch("backend.api.middleware.rbac.get_session")
def test_api_submit_exclusion_invalid_type(mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    payload = {
        "fir_id": "FIR1",
        "accused_id": "ACC1",
        "exclusion_type": "invalid_type",
        "reason": "Invalid"
    }
    response = client.post("/api/investigation/exclude", json=payload, headers={"Authorization": "Bearer mocktoken"})
    assert response.status_code == 400

@patch("backend.api.middleware.rbac.get_session")
def test_api_submit_exclusion_missing_alibi_window(mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    payload = {
        "fir_id": "FIR1",
        "accused_id": "ACC1",
        "exclusion_type": "alibi_confirmed",
        "reason": "Has an alibi"
    }
    response = client.post("/api/investigation/exclude", json=payload, headers={"Authorization": "Bearer mocktoken"})
    assert response.status_code == 400

@patch("backend.api.middleware.rbac.get_session")
@patch("backend.api.routes.exclusions.reverse_exclusion")
def test_api_reverse_exclusion(mock_reverse, mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    
    response = client.post(
        "/api/investigation/exclude/exclusion_123/reverse", 
        json={"reversed_reason": "Alibi was false"},
        headers={"Authorization": "Bearer mocktoken"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "reversed"
    mock_reverse.assert_called_once()
