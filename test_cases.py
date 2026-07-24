import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_create_case_unauthorized():
    response = client.post("/api/cases", json={"title": "Test Case"})
    assert response.status_code == 401


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_create_case_authorized(mock_get_session, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = None  # user_cases:officer_1 starts empty

    response = client.post(
        "/api/cases",
        json={"title": "Chain snatching cluster", "crime_no": "123/2024", "district": "Mysuru"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "Chain snatching cluster"
    assert body["collaborators"] == ["officer_1"]
    assert body["created_by"] == "officer_1"
    # case doc, case_sessions doc, and user_cases index all written
    assert mock_set.call_count == 3


# BUG FIX regression coverage: _require_collaborator used to return a distinct
# 404 for a nonexistent case_id vs 403 for "exists but you're not on it",
# letting a caller use the status code as an existence oracle. Both scenarios
# below must return an identical 403 body.
@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.get_user", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_add_collaborator_nonexistent_case_returns_403(mock_get_session, mock_get_user, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = None  # case:{id} doesn't exist

    response = client.post(
        "/api/cases/c_deadbeef/collaborators",
        json={"username": "officer_2"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this case"}
    mock_get_user.assert_not_called()


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.get_user", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_add_collaborator_exists_but_not_a_collaborator_returns_identical_403(
    mock_get_session, mock_get_user, mock_get, mock_set
):
    mock_get_session.return_value = {"username": "outsider", "role": "inspector"}
    existing_case = {
        "case_id": "c_real0001",
        "title": "Real case",
        "collaborators": ["officer_1"],
    }
    mock_get.return_value = {"value": json.dumps(existing_case)}

    response = client.post(
        "/api/cases/c_real0001/collaborators",
        json={"username": "officer_2"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "Not authorized for this case"}
    mock_get_user.assert_not_called()


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.get_user", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_add_collaborator_success(mock_get_session, mock_get_user, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    existing_case = {
        "case_id": "c_real0001",
        "title": "Real case",
        "collaborators": ["officer_1"],
    }

    # First read is the case doc (inside get_case_lock -> _require_collaborator),
    # second read is user_cases:officer_2 inside _add_case_to_user_index.
    mock_get.side_effect = [
        {"value": json.dumps(existing_case)},
        None,
    ]
    mock_get_user.return_value = {"username": "officer_2", "role": "constable"}

    response = client.post(
        "/api/cases/c_real0001/collaborators",
        json={"username": "officer_2"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 200
    assert response.json()["collaborators"] == ["officer_1", "officer_2"]
    # one write for the updated case doc, one for officer_2's user_cases index
    assert mock_set.call_count == 2


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.get_user", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_add_collaborator_unknown_officer_rejected(mock_get_session, mock_get_user, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    existing_case = {
        "case_id": "c_real0001",
        "title": "Real case",
        "collaborators": ["officer_1"],
    }
    mock_get.return_value = {"value": json.dumps(existing_case)}
    mock_get_user.return_value = None  # target username not a real officer

    response = client.post(
        "/api/cases/c_real0001/collaborators",
        json={"username": "ghost"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 404
