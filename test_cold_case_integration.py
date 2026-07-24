import os
import sys
import pytest
import asyncio
from fastapi.testclient import TestClient

os.environ["MOCK_NOSQL_ONLY"] = "true"
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

MOCK_DB_PATH = os.path.join(os.path.dirname(__file__), ".nosql_mock_db.json")

def clear_mock_db():
    if os.path.exists(MOCK_DB_PATH):
        try:
            os.remove(MOCK_DB_PATH)
        except Exception:
            pass

async def mock_get_session(token: str):
    if token == "mock-valid-token":
        return {"username": "dysp1", "role": "dysp", "display_name": "DySP Rao"}
    return None

import shared.auth
shared.auth.get_session = mock_get_session

import backend.api.middleware.rbac
backend.api.middleware.rbac.get_session = mock_get_session

from backend.main import app
client = TestClient(app)

AUTH = {"Authorization": "Bearer mock-valid-token"}


def test_api_list_review_queue_empty():
    """GET /api/review-queue with empty store must return [] with status 200."""
    print("\n[*] Testing GET /api/review-queue (Empty Queue)...")
    clear_mock_db()  # guarantee clean state

    response = client.get("/api/review-queue", headers=AUTH)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text}"
    )
    body = response.json()
    assert isinstance(body, list), f"Expected list response, got {type(body)}"
    assert len(body) == 0, f"Expected empty list, got {len(body)} items"
    print("  ✅ GET /api/review-queue (Empty) passed!")


def test_api_list_review_queue_unauthenticated():
    """GET /api/review-queue without auth must return 401."""
    print("\n[*] Testing GET /api/review-queue (No Auth)...")
    response = client.get("/api/review-queue")
    assert response.status_code == 401, (
        f"Expected 401 for missing auth, got {response.status_code}"
    )
    response2 = client.get("/api/review-queue", headers={"Authorization": "Bearer bad-token"})
    assert response2.status_code == 401, (
        f"Expected 401 for invalid token, got {response2.status_code}"
    )
    print("  ✅ Unauthenticated access rejected (401) passed!")


def test_api_resolve_review_item_success():
    """Full lifecycle: push item → GET appears → POST resolve → GET disappears."""
    print("\n[*] Testing POST /api/review-queue/{id}/resolve...")
    clear_mock_db()  # FIXED: always clean before each test to avoid state leakage

    from shared.review_queue_models import ReviewQueueItem
    from shared.review_queue_engine import push_review_item

    item = ReviewQueueItem(
        item_id="alert-test-999",
        item_type="cold_case_match",
        fir_id="FIR-1",
        related_fir_id="FIR-2",
        summary="Matches case",
        score=0.85,
        created_date="2026-07-24T12:00:00Z"
    )

    # FIXED: use asyncio.run() instead of deprecated asyncio.get_event_loop()
    # which raises DeprecationWarning in Python 3.12+ and may hang in pytest-asyncio contexts.
    asyncio.run(push_review_item(item))

    # Verify it shows up in list
    list_res = client.get("/api/review-queue", headers=AUTH)
    assert list_res.status_code == 200, f"Expected 200, got {list_res.status_code}"
    items = list_res.json()
    assert len(items) == 1, f"Expected exactly 1 item, got {len(items)}"
    assert items[0]["item_id"] == "alert-test-999"
    assert items[0]["status"] == "pending"

    # Resolve it
    payload = {"status": "reviewed"}
    response = client.post("/api/review-queue/alert-test-999/resolve", headers=AUTH, json=payload)
    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}. Body: {response.text}"
    )
    data = response.json()
    assert data["status"] == "reviewed", f"Expected 'reviewed', got '{data['status']}'"
    # reviewed_by comes from the RBAC session (mock: username='dysp1'), not the request body
    assert data["reviewed_by"] == "dysp1", f"Expected 'dysp1' from RBAC session, got '{data['reviewed_by']}'"
    assert data["reviewed_date"] is not None

    # Verify it no longer appears in pending list
    list_res2 = client.get("/api/review-queue", headers=AUTH)
    assert list_res2.status_code == 200
    assert len(list_res2.json()) == 0, (
        f"Expected empty pending queue after resolve, got {len(list_res2.json())} items"
    )
    print("  ✅ POST /api/review-queue/{id}/resolve lifecycle passed!")


def test_api_resolve_nonexistent_item():
    """POST /api/review-queue/{id}/resolve for a non-existent item must return 404."""
    print("\n[*] Testing resolve on non-existent item...")
    clear_mock_db()
    payload = {"status": "reviewed"}
    response = client.post("/api/review-queue/DOES-NOT-EXIST/resolve", headers=AUTH, json=payload)
    assert response.status_code == 404, (
        f"Expected 404 for non-existent item, got {response.status_code}"
    )
    print("  ✅ 404 for non-existent item passed!")


def test_api_resolve_invalid_status():
    """POST /api/review-queue/{id}/resolve with invalid status must return 400."""
    print("\n[*] Testing resolve with invalid status...")
    clear_mock_db()

    from shared.review_queue_models import ReviewQueueItem
    from shared.review_queue_engine import push_review_item

    item = ReviewQueueItem(
        item_id="alert-invalid-status",
        item_type="cold_case_match",
        fir_id="FIR-X",
        summary="Test",
        score=0.8,
        created_date="2026-07-24T12:00:00Z"
    )
    asyncio.run(push_review_item(item))

    payload = {"status": "WRONG_STATUS"}
    response = client.post("/api/review-queue/alert-invalid-status/resolve", headers=AUTH, json=payload)
    assert response.status_code == 422, (
        f"Expected 422 (Pydantic validation error) for invalid status 'WRONG_STATUS', got {response.status_code}. Body: {response.text}"
    )
    print("  ✅ 400 for invalid status passed!")


def test_api_resolve_missing_fields():
    """POST /api/review-queue/{id}/resolve with missing required fields must return 422."""
    print("\n[*] Testing resolve with missing status field...")
    clear_mock_db()

    from shared.review_queue_models import ReviewQueueItem
    from shared.review_queue_engine import push_review_item

    item = ReviewQueueItem(
        item_id="alert-missing-fields",
        item_type="cold_case_match",
        fir_id="FIR-Y",
        summary="Test",
        score=0.8,
        created_date="2026-07-24T12:00:00Z"
    )
    asyncio.run(push_review_item(item))

    # Missing 'status' — required field
    response = client.post("/api/review-queue/alert-missing-fields/resolve", headers=AUTH, json={})
    assert response.status_code == 422, (
        f"Expected 422 for missing status, got {response.status_code}. Body: {response.text}"
    )
    print("  ✅ 400/422 for missing fields passed!")


if __name__ == "__main__":
    test_api_list_review_queue_empty()
    test_api_list_review_queue_unauthenticated()
    test_api_resolve_review_item_success()
    test_api_resolve_nonexistent_item()
    test_api_resolve_invalid_status()
    test_api_resolve_missing_fields()
    print("\n🎉 ALL INTEGRATION TESTS PASSED!")
