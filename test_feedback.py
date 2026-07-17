import pytest
from unittest.mock import patch, AsyncMock
from shared.feedback_models import CorrectionEvent, MethodologyTrust
from shared.feedback_engine import (
    _smoothed_trust,
    _sanitize_scope_part,
    _narrow_scope_key,
    get_trust_weight,
    record_feedback_event,
    get_session_penalized_ids,
    PRIOR_TRUST,
    TRUST_WEIGHT_FLOOR
)
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_sanitize_scope_part_escapes_delimiter():
    # BUG FIX regression coverage: raw ":" in a client-controlled edge_type/
    # crime_type value must never survive into the joined scope key unescaped,
    # or a crafted edge_type could forge a key belonging to a different scope.
    assert _sanitize_scope_part("SHARED_MO") == "SHARED_MO"
    assert ":" not in _sanitize_scope_part("SHARED_MO::burglary")
    assert "%" not in _sanitize_scope_part("100%").replace("%25", "")


def test_narrow_scope_key_collision_prevented():
    # An attacker submitting edge_type="SHARED_MO::burglary" with crime_type=None
    # (so _narrow_scope_key is never even called for them) must not be able to
    # produce the same broad-scope key string a genuine narrow-scope pair uses.
    genuine_narrow_key = _narrow_scope_key("SHARED_MO", "burglary")
    crafted_broad_equivalent = _sanitize_scope_part("SHARED_MO::burglary")
    assert genuine_narrow_key != crafted_broad_equivalent

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

@pytest.mark.anyio
@patch("shared.feedback_engine.nosql_set", new_callable=AsyncMock)
@patch("shared.feedback_engine.nosql_get", new_callable=AsyncMock)
async def test_record_feedback_event_increments_broad_and_narrow(mock_get, mock_set, anyio_backend="asyncio"):
    # No existing trust records -- both broad and narrow start fresh.
    mock_get.return_value = None
    event = CorrectionEvent(
        event_id="ev1", session_id="s1", officer_id="officer_1", timestamp="2024-01-01T00:00:00",
        query_text="q", edge_type="SHARED_MO", crime_type="burglary", edge_id=None,
        verdict="confirmed",
    )
    await record_feedback_event(event)

    # correction:{event_id} + trust:SHARED_MO (broad) + trust:SHARED_MO::burglary (narrow)
    assert mock_set.call_count == 3
    written_keys = [call.args[0] for call in mock_set.call_args_list]
    assert "correction:ev1" in written_keys
    assert "trust:SHARED_MO" in written_keys
    assert f"trust:{_narrow_scope_key('SHARED_MO', 'burglary')}" in written_keys


@pytest.mark.anyio
@patch("shared.feedback_engine.nosql_set", new_callable=AsyncMock)
@patch("shared.feedback_engine.nosql_get", new_callable=AsyncMock)
async def test_record_feedback_event_negative_verdict_applies_session_penalty(mock_get, mock_set, anyio_backend="asyncio"):
    mock_get.return_value = None
    event = CorrectionEvent(
        event_id="ev2", session_id="s1", officer_id="officer_1", timestamp="2024-01-01T00:00:00",
        query_text="q", edge_type="SHARED_MO", crime_type=None, edge_id="edge_456",
        verdict="corrected",
    )
    await record_feedback_event(event)

    written_keys = [call.args[0] for call in mock_set.call_args_list]
    assert "session_penalty:s1" in written_keys


@pytest.mark.anyio
@patch("shared.feedback_engine.nosql_get", new_callable=AsyncMock)
async def test_get_session_penalized_ids_empty_when_unset(mock_get, anyio_backend="asyncio"):
    mock_get.return_value = None
    result = await get_session_penalized_ids("s1")
    assert result == set()


@patch("backend.api.middleware.rbac.get_session")
@patch("backend.api.routes.feedback.record_feedback_event", new_callable=AsyncMock)
@patch("backend.api.routes.feedback.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.feedback.nosql_get", new_callable=AsyncMock)
def test_api_submit_feedback(mock_get, mock_set, mock_record, mock_get_session):
    # BUG FIX (test isolation): this test previously left the route's own
    # rate-limit check (_enforce_rate_limit, added after this test was
    # originally written) hitting the real nosql_get/nosql_set -- only
    # record_feedback_event was mocked. That meant every run of this test
    # against a real Catalyst NoSQL backend permanently incremented a real
    # feedback_rate:officer_1:SHARED_MO counter; after enough accumulated
    # runs across a long session the real counter crossed FEEDBACK_RATE_LIMIT
    # and this test started failing with a genuine 429 instead of 200 --
    # not an application bug, a test-isolation bug. Mocking nosql_get/nosql_set
    # here (nosql_get returns None -- "no prior submissions this window")
    # makes the rate-limit check deterministic and stops writing real data.
    mock_get.return_value = None
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
