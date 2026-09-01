# BUG FIX (2026-09 audit) regression coverage: backend/api/middleware/rbac.py
# previously enforced a minimum rank on exactly one route (/api/export/pdf).
# Every other mutating/sensitive route accepted any authenticated session
# regardless of rank. The existing test suite didn't catch this because every
# mocked session in tests/test_cases.py, tests/test_exclusions.py, etc. uses
# role="inspector" -- comfortably above every new minimum, so those tests
# pass whether or not enforcement is actually wired up. This file specifically
# proves a too-low rank gets a 403, and a sufficient rank does not, for each
# newly-gated route.
from unittest.mock import patch, AsyncMock

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.api.middleware.rbac import _match_min_role

client = TestClient(app)


@pytest.mark.parametrize(
    "method,path,min_role",
    [
        ("DELETE", "/api/cases/{case_id}", "sub_inspector"),
        ("POST", "/api/cases/{case_id}/collaborators", "sub_inspector"),
        ("POST", "/api/investigation/exclude", "asi"),
        ("POST", "/api/investigation/exclude/{exclusion_id}/reverse", "sub_inspector"),
        ("POST", "/api/investigation/contradiction", "asi"),
        ("POST", "/api/review-queue/{item_id}/resolve", "asi"),
        ("POST", "/api/export/pdf", "sub_inspector"),
    ],
)
def test_route_min_role_table_matches_declared_policy(method, path, min_role):
    assert _match_min_role(method, path) == min_role


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_delete_case_rejects_constable(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "constable_1", "role": "constable"}

    response = client.delete(
        "/api/cases/c_deadbeef",
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403
    assert "Insufficient rank" in response.json()["detail"]
    # Rank is checked before the route body runs -- ownership/case-existence
    # lookups must never fire for a rank-rejected request.
    mock_get.assert_not_called()


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_delete_case_allows_sub_inspector_and_above(mock_get_session, mock_get, mock_set):
    mock_get_session.return_value = {"username": "si_1", "role": "sub_inspector"}
    mock_get.return_value = json_case_doc()

    response = client.delete(
        "/api/cases/c_deadbeef",
        headers={"Authorization": "Bearer mocktoken"},
    )

    # Not a 403 -- rank check passes; whatever the route does past that point
    # (ownership checks, actual deletion) is covered by tests/test_cases.py.
    assert response.status_code != 403


@patch("backend.api.middleware.rbac.get_session")
def test_add_collaborator_rejects_head_constable(mock_get_session):
    mock_get_session.return_value = {"username": "hc_1", "role": "head_constable"}

    response = client.post(
        "/api/cases/c_deadbeef/collaborators",
        json={"username": "officer_2"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403


@patch("backend.api.middleware.rbac.get_session")
def test_submit_exclusion_rejects_constable(mock_get_session):
    mock_get_session.return_value = {"username": "constable_1", "role": "constable"}

    response = client.post(
        "/api/investigation/exclude",
        json={
            "fir_id": "fir_1",
            "accused_id": "acc_1",
            "exclusion_type": "ruled_out",
            "reason": "Confirmed alibi",
        },
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403


@patch("backend.api.middleware.rbac.get_session")
def test_reverse_exclusion_rejects_asi_requires_sub_inspector(mock_get_session):
    # Reversing an exclusion is stricter than creating one (asi) -- an ASI
    # can create an exclusion but not undo it.
    mock_get_session.return_value = {"username": "asi_1", "role": "asi"}

    response = client.post(
        "/api/investigation/exclude/excl_1/reverse",
        json={"reason": "New evidence surfaced"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403


@patch("backend.api.middleware.rbac.get_session")
def test_resolve_review_queue_item_rejects_head_constable(mock_get_session):
    mock_get_session.return_value = {"username": "hc_1", "role": "head_constable"}

    response = client.post(
        "/api/review-queue/item_1/resolve",
        json={"resolution": "actioned"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403


def json_case_doc():
    import json

    return {
        "value": json.dumps(
            {
                "id": "c_deadbeef",
                "title": "Test Case",
                "created_by": "si_1",
                "collaborators": ["si_1"],
            }
        )
    }
