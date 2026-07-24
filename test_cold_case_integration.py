import os
import sys
import pytest
from fastapi.testclient import TestClient

os.environ["MOCK_NOSQL_ONLY"] = "true"
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

def test_api_list_review_queue_empty():
    print("\n[*] Testing GET /api/review-queue (Empty Queue)...")
    # Clean mock database
    MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

    headers = {"Authorization": "Bearer mock-valid-token"}
    response = client.get("/api/review-queue", headers=headers)
    print(f"Status Code: {response.status_code}, Body: {response.text}")
    assert response.status_code == 200
    assert response.json() == []
    print("  ✅ GET /api/review-queue (Empty) passed!")

def test_api_resolve_review_item_success():
    print("\n[*] Testing POST /api/review-queue/{id}/resolve...")
    # Add a mock alert to DB first
    from shared.review_queue_models import ReviewQueueItem
    from shared.review_queue_engine import push_review_item
    import asyncio
    
    item = ReviewQueueItem(
        item_id="alert-test-999",
        item_type="cold_case_match",
        fir_id="FIR-1",
        related_fir_id="FIR-2",
        summary="Matches case",
        score=0.85,
        created_date="2026-07-24T12:00:00Z"
    )
    # Run the async push in the current loop or create one
    loop = asyncio.get_event_loop()
    if loop.is_running():
        # This will be true if run inside pytest async, but TestClient runs synchronously
        # We can run it using loop.create_task or run_coroutine_threadsafe if needed,
        # but since we are running in pytest, we'll just run it synchronously
        import nest_asyncio
        nest_asyncio.apply()
        loop.run_until_complete(push_review_item(item))
    else:
        loop.run_until_complete(push_review_item(item))
    
    headers = {"Authorization": "Bearer mock-valid-token"}
    # Verify it shows up in list
    list_res = client.get("/api/review-queue", headers=headers)
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1
    assert any(i["item_id"] == "alert-test-999" for i in list_res.json())
    
    # Resolve it
    payload = {"status": "reviewed", "reviewed_by": "dysp1"}
    response = client.post("/api/review-queue/alert-test-999/resolve", headers=headers, json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "reviewed"
    assert data["reviewed_by"] == "dysp1"
    assert data["reviewed_date"] is not None
    
    # Verify it is no longer pending in lists
    list_res2 = client.get("/api/review-queue", headers=headers)
    assert not any(i["item_id"] == "alert-test-999" for i in list_res2.json())
    print("  ✅ POST /api/review-queue/{id}/resolve passed!")

if __name__ == "__main__":
    test_api_list_review_queue_empty()
    test_api_resolve_review_item_success()
