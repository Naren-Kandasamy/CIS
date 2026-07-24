import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_get_session_unauthorized():
    response = client.get("/api/sessions/s_abcd1234")
    assert response.status_code == 401


@patch("backend.api.routes.sessions.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_get_session_not_found(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = None  # session_meta:{id} doesn't exist

    response = client.get("/api/sessions/s_deadbeef", headers={"Authorization": "Bearer mocktoken"})

    assert response.status_code == 404


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.sessions.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_get_session_denied_for_non_collaborator(mock_get_session, mock_sessions_get, mock_cases_get):
    # BUG FIX regression coverage: a session's access is inherited entirely
    # from its parent case's collaborator list, via cases.py's
    # _require_collaborator -- an officer not on the case must be denied even
    # though they know a real session_id.
    mock_get_session.return_value = {"username": "outsider", "role": "inspector"}
    mock_sessions_get.return_value = {
        "value": json.dumps({"session_id": "s_deadbeef", "case_id": "c_real0001", "created_by": "officer_1"})
    }
    mock_cases_get.return_value = {
        "value": json.dumps({"case_id": "c_real0001", "collaborators": ["officer_1"]})
    }

    response = client.get("/api/sessions/s_deadbeef", headers={"Authorization": "Bearer mocktoken"})

    assert response.status_code == 403


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.sessions.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_get_session_allowed_for_collaborator(mock_get_session, mock_sessions_get, mock_cases_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}

    session_meta = {"session_id": "s_deadbeef", "case_id": "c_real0001", "created_by": "officer_1"}
    case_doc = {"case_id": "c_real0001", "collaborators": ["officer_1"]}
    history = [{"q": "any leads?", "a": "none yet"}]

    def sessions_get_side_effect(key):
        if key == "session_meta:s_deadbeef":
            return {"value": json.dumps(session_meta)}
        if key == "history:s_deadbeef":
            return {"value": json.dumps(history)}
        return None

    mock_sessions_get.side_effect = sessions_get_side_effect
    mock_cases_get.return_value = {"value": json.dumps(case_doc)}

    response = client.get("/api/sessions/s_deadbeef", headers={"Authorization": "Bearer mocktoken"})

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["case_id"] == "c_real0001"
    assert body["history"] == history
