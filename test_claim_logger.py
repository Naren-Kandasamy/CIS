import pytest
import json
from unittest.mock import patch, AsyncMock
from shared.claim_logger import log_claim, check_and_flag_contradicted_claims
from shared.claim_models import ClaimRecord
from shared.review_queue_models import ReviewQueueItem

@pytest.mark.anyio
@patch("shared.claim_logger.nosql_set", new_callable=AsyncMock)
@patch("shared.claim_logger.nosql_get", new_callable=AsyncMock)
async def test_log_claim_indexing(mock_get, mock_set, anyio_backend="asyncio"):
    # Mocking nosql_get to return an empty index initially
    mock_get.return_value = None
    
    await log_claim(
        fir_id="FIR123",
        accused_id="ACC456",
        evidence_ref="node:123",
        confidence_tier="HIGH",
        snippet="Suspect found near scene"
    )
    
    assert mock_set.call_count == 2
    # Check that the actual claim was saved
    claim_call = mock_set.call_args_list[0]
    assert claim_call[0][0].startswith("claim:")
    
    # Check that the index was updated
    index_call = mock_set.call_args_list[1]
    assert index_call[0][0] == "claim_index:FIR123"
    assert "claim:" not in index_call[0][1] # Should just be a JSON array of claim IDs

@pytest.mark.anyio
@patch("shared.claim_logger.push_review_item", new_callable=AsyncMock)
@patch("shared.claim_logger.nosql_set", new_callable=AsyncMock)
@patch("shared.claim_logger.nosql_get", new_callable=AsyncMock)
async def test_check_and_flag_contradiction(mock_get, mock_set, mock_push, anyio_backend="asyncio"):
    # Setup mock data
    claim_id = "test_claim_id"
    mock_index = {"value": json.dumps([claim_id])}
    mock_claim = {
        "value": json.dumps({
            "claim_id": claim_id,
            "fir_id": "FIR123",
            "accused_id": "ACC456",
            "confidence_tier": "HIGH",
            "synthesized_snippet": "He was there",
            "timestamp": "2024-01-01T00:00:00",
            "contradicted": False
        })
    }
    
    # nosql_get called first for the index, then for the claim itself
    mock_get.side_effect = [mock_index, mock_claim]
    
    # Execute the tripwire
    await check_and_flag_contradicted_claims(fir_id="FIR123", accused_id="ACC456", reason="Confirmed Alibi")
    
    # Assert the claim was updated to contradicted=True
    assert mock_set.call_count == 1
    updated_claim = json.loads(mock_set.call_args_list[0][0][1])
    assert updated_claim["contradicted"] is True
    assert updated_claim["contradicted_date"] is not None
    
    # Assert the alert was pushed to the review queue
    assert mock_push.call_count == 1
    alert = mock_push.call_args_list[0][0][0]
    assert isinstance(alert, ReviewQueueItem)
    assert alert.item_type == "contradiction_alert"
    assert "Confirmed Alibi" in alert.summary
