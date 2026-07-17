import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from backend.main import app
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item, get_pending_review_items

client = TestClient(app)

@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
@patch("shared.review_queue_engine.nosql_set", new_callable=AsyncMock)
async def test_push_and_get_review_items(mock_set, mock_get, anyio_backend="asyncio"):
    # Mocking nosql_get to return an empty index first, then the item
    mock_get.side_effect = [
        None,  # First call to get index
        {"value": '["item_123"]'},  # Second call to get index
        {"value": '{"item_id": "item_123", "item_type": "cold_case_match", "fir_id": "FIR1", "summary": "Test match", "created_date": "2024-01-01T00:00:00", "status": "pending"}'} # Call to get actual item
    ]
    
    item = ReviewQueueItem(
        item_id="item_123",
        item_type="cold_case_match",
        fir_id="FIR1",
        summary="Test match",
        created_date=datetime.now(timezone.utc).isoformat()
    )
    
    # Test push
    await push_review_item(item)
    assert mock_set.call_count == 2 # Once for item, once for updating index
    
    # Test get pending
    items = await get_pending_review_items("FIR1")
    assert len(items) == 1
    assert items[0].item_id == "item_123"
    assert items[0].fir_id == "FIR1"

@patch("backend.api.routes.review_queue.get_review_item", new_callable=AsyncMock)
@patch("backend.api.routes.review_queue.nosql_set", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_resolve_review_item_api(mock_get_session, mock_set, mock_get_item):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    
    mock_get_item.return_value = ReviewQueueItem(
        item_id="item_123",
        item_type="cold_case_match",
        fir_id="FIR1",
        summary="Test match",
        created_date="2024-01-01T00:00:00"
    )
    
    payload = {"status": "reviewed"}
    
    response = client.post("/api/review-queue/item_123/resolve", json=payload, headers={"Authorization": "Bearer mocktoken"})
    assert response.status_code == 200
    assert response.json()["item"]["status"] == "reviewed"
    assert response.json()["item"]["reviewed_by"] == "officer_1"
    
    # Check that nosql_set was called to save the updated item
    mock_set.assert_called_once()
