from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


@patch("backend.api.routes.auth.create_session", new_callable=AsyncMock)
@patch("backend.api.routes.auth.authenticate", new_callable=AsyncMock)
@patch("backend.api.routes.auth.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.auth.nosql_get", new_callable=AsyncMock)
def test_login_success(mock_get, mock_set, mock_auth, mock_create_session):
    mock_get.return_value = None  # no prior failures
    mock_auth.return_value = {"username": "officer_1", "role": "inspector", "display_name": "Officer One"}
    mock_create_session.return_value = "real-session-token"

    response = client.post("/api/auth/login", json={"username": "officer_1", "password": "correct-horse"})

    assert response.status_code == 200
    body = response.json()
    assert body["token"] == "real-session-token"
    assert body["role"] == "inspector"
    mock_auth.assert_called_once_with("officer_1", "correct-horse")


@patch("backend.api.routes.auth.create_session", new_callable=AsyncMock)
@patch("backend.api.routes.auth.authenticate", new_callable=AsyncMock)
@patch("backend.api.routes.auth.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.auth.nosql_get", new_callable=AsyncMock)
def test_login_wrong_password_increments_failure_counter(mock_get, mock_set, mock_auth, mock_create_session):
    mock_get.return_value = None
    mock_auth.return_value = None  # authenticate() failed

    response = client.post("/api/auth/login", json={"username": "officer_1", "password": "wrong"})

    assert response.status_code == 401
    mock_set.assert_called_once_with("loginfail:officer_1", "1", ttl=15 * 60)
    mock_create_session.assert_not_called()


@patch("backend.api.routes.auth.authenticate", new_callable=AsyncMock)
@patch("backend.api.routes.auth.nosql_get", new_callable=AsyncMock)
def test_login_locked_out_after_max_failures(mock_get, mock_auth):
    # BUG FIX regression coverage: once the failure counter reaches the cap,
    # the route must reject with 429 before ever calling authenticate() again.
    mock_get.return_value = {"value": "5"}

    response = client.post("/api/auth/login", json={"username": "officer_1", "password": "guess"})

    assert response.status_code == 429
    mock_auth.assert_not_called()


@patch("backend.api.routes.auth.invalidate_session", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_logout_revokes_token(mock_get_session, mock_invalidate):
    # /api/auth/logout is not a PUBLIC_PATH, so RBACMiddleware itself requires
    # a valid session before the route body ever runs -- get_session must be
    # mocked to simulate the still-valid token the client is logging out with.
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}

    response = client.post("/api/auth/logout", headers={"Authorization": "Bearer some-real-token"})

    assert response.status_code == 200
    assert response.json() == {"status": "logged_out"}
    mock_invalidate.assert_called_once_with("some-real-token")


def test_logout_unauthenticated_is_rejected_by_rbac():
    # No Authorization header at all -- RBACMiddleware rejects with 401
    # before backend.api.routes.auth.logout is ever reached.
    response = client.post("/api/auth/logout")
    assert response.status_code == 401
