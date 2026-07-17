import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from backend.main import app
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item, get_pending_review_items, get_review_item

client = TestClient(app)

@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
@patch("shared.review_queue_engine.nosql_set", new_callable=AsyncMock)
async def test_push_and_get_review_items(mock_set, mock_get, anyio_backend="asyncio"):
    # Mocking nosql_get to return an empty index first, then the item.
    # BUG FIX: push_review_item's index update now verifies its own write
    # landed (retries if a concurrent writer clobbered it -- see
    # shared/review_queue_engine.py's cross-instance race fix), which reads
    # the index a second time before returning. One extra scripted response
    # for that verify-read, matching the real new call sequence.
    mock_get.side_effect = [
        None,  # push_review_item: initial index read (empty)
        {"value": '["item_123"]'},  # push_review_item: verify-after-write read
        {"value": '["item_123"]'},  # get_pending_review_items: index read
        {"value": '{"item_id": "item_123", "item_type": "cold_case_match", "fir_id": "FIR1", "summary": "Test match", "created_date": "2024-01-01T00:00:00", "status": "pending"}'} # get_pending_review_items: per-item read
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

@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
async def test_get_pending_review_items_skips_malformed_row(mock_get, anyio_backend="asyncio"):
    # BUG FIX regression coverage: one malformed/schema-drifted row used to
    # raise uncaught and 500 the entire queue listing for every officer.
    def get_side_effect(key):
        if key == "review_queue_index":
            return {"value": '["item_good", "item_bad"]'}
        if key == "review_queue:item_good":
            return {"value": '{"item_id": "item_good", "item_type": "cold_case_match", "fir_id": "FIR1", "summary": "ok", "created_date": "2024-01-02T00:00:00", "status": "pending"}'}
        if key == "review_queue:item_bad":
            return {"value": '{"item_id": "item_bad", "not_a_real_field": true}'}  # missing required fields
        return None

    mock_get.side_effect = get_side_effect
    items = await get_pending_review_items()
    assert len(items) == 1
    assert items[0].item_id == "item_good"


@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
async def test_get_pending_review_items_filters_by_fir_id(mock_get, anyio_backend="asyncio"):
    def get_side_effect(key):
        if key == "review_queue_index":
            return {"value": '["item_a", "item_b"]'}
        if key == "review_queue:item_a":
            return {"value": '{"item_id": "item_a", "item_type": "cold_case_match", "fir_id": "FIR1", "summary": "a", "created_date": "2024-01-02T00:00:00", "status": "pending"}'}
        if key == "review_queue:item_b":
            return {"value": '{"item_id": "item_b", "item_type": "cold_case_match", "fir_id": "FIR2", "related_fir_id": "FIR1", "summary": "b", "created_date": "2024-01-01T00:00:00", "status": "pending"}'}
        return None

    mock_get.side_effect = get_side_effect
    items = await get_pending_review_items(fir_id="FIR1")
    # item_b matches via related_fir_id even though its own fir_id is FIR2
    assert {i.item_id for i in items} == {"item_a", "item_b"}


@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
async def test_get_review_item_returns_none_for_malformed_row(mock_get, anyio_backend="asyncio"):
    mock_get.return_value = {"value": '{"item_id": "item_bad", "not_a_real_field": true}'}
    result = await get_review_item("item_bad")
    assert result is None


@pytest.mark.anyio
@patch("shared.review_queue_engine.nosql_set", new_callable=AsyncMock)
@patch("shared.review_queue_engine.nosql_get", new_callable=AsyncMock)
async def test_push_review_item_retries_until_verified(mock_get, mock_set, anyio_backend="asyncio"):
    # BUG FIX regression coverage: the write-then-verify loop must retry (up
    # to max_attempts) if the verify-read doesn't reflect the just-written
    # item_id -- e.g. a concurrent writer's index landed in between.
    item = ReviewQueueItem(
        item_id="item_retry", item_type="cold_case_match", fir_id="FIR1",
        summary="test", created_date=datetime.now(timezone.utc).isoformat(),
    )
    mock_get.side_effect = [
        None,                            # attempt 1: initial index read (empty)
        {"value": '["someone_elses_item"]'},  # attempt 1: verify-read -- our id got clobbered
        {"value": '["someone_elses_item"]'},  # attempt 2: initial index read
        {"value": '["someone_elses_item", "item_retry"]'},  # attempt 2: verify-read -- now present
    ]
    await push_review_item(item)
    # 1 for the item itself + 2 for the two index-write attempts
    assert mock_set.call_count == 3


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
