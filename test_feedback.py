import pytest
from unittest.mock import patch, AsyncMock
from shared.feedback_models import CorrectionEvent, MethodologyTrust
from shared.feedback_engine import (
    _smoothed_trust,
    get_trust_weight,
    record_feedback_event,
    PRIOR_TRUST,
    TRUST_WEIGHT_FLOOR
)
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

def test_smoothed_trust_math():
    # Zero observations should return exact prior
    assert _smoothed_trust(0, 0) == PRIOR_TRUST
    
    # One correction, zero confirmations
    # (0 + 10*0.7) / (1 + 10) = 7 / 11 = 0.6363...
    assert round(_smoothed_trust(0, 1), 3) == 0.636
    
    # 50 corrections should approach but not go below the floor
    heavy_penalty = _smoothed_trust(0, 50)
    assert heavy_penalty >= TRUST_WEIGHT_FLOOR
    assert heavy_penalty < 0.35 # It should drop significantly

@pytest.mark.anyio
@patch("shared.feedback_engine._load_trust")
async def test_fallback_broad_scope_when_sparse(mock_load_trust, anyio_backend="asyncio"):
    # Mock returning sparse narrow scope data
    def mock_load(key):
        if "::" in key:
            return MethodologyTrust(scope_key=key, confirmations=1, corrections=1)
        return MethodologyTrust(scope_key=key, confirmations=100, corrections=100)
    mock_load_trust.side_effect = mock_load
    
    # Since narrow scope has 2 < 15 samples, it should fallback to broad (100/100)
    weight = await get_trust_weight("SHARED_MO", "burglary")
    assert round(weight, 3) == round(_smoothed_trust(100, 100), 3)

@pytest.mark.anyio
@patch("shared.feedback_engine._load_trust")
async def test_narrow_scope_when_sufficient(mock_load_trust, anyio_backend="asyncio"):
    # Mock returning sufficient narrow scope data
    def mock_load(key):
        if "::" in key:
            return MethodologyTrust(scope_key=key, confirmations=0, corrections=20)
        return MethodologyTrust(scope_key=key, confirmations=100, corrections=100)
    mock_load_trust.side_effect = mock_load
    
    # Narrow has 20 samples, so it should NOT fallback to broad
    weight = await get_trust_weight("SHARED_MO", "burglary")
    assert round(weight, 3) == round(_smoothed_trust(0, 20), 3)
    assert round(weight, 3) != round(_smoothed_trust(100, 100), 3)

@patch("backend.api.middleware.rbac.get_session")
@patch("backend.api.routes.feedback.record_feedback_event", new_callable=AsyncMock)
def test_api_submit_feedback(mock_record, mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    
    payload = {
        "session_id": "session123",
        "query_text": "Who is connected?",
        "edge_type": "SHARED_MO",
        "crime_type": "burglary",
        "edge_id": "edge_456",
        "verdict": "corrected",
        "explanation": "MO is actually different"
    }
    
    response = client.post("/api/feedback/correction", json=payload, headers={"Authorization": "Bearer mocktoken"})
    assert response.status_code == 200
    mock_record.assert_called_once()
