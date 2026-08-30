import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


# sse_starlette's EventSourceResponse keeps the generator alive across the
# request; chaining several real SSE responses through one TestClient/process
# can hit a third-party "Event object is bound to a different event loop"
# teardown error unrelated to the route logic under test (see this session's
# notes on /api/query's IDOR test). Stubbing stream_job_status to a single
# short-lived generator sidesteps that entirely while still proving the route
# reached EventSourceResponse construction (i.e. authorization succeeded).
async def _fake_stream(job_id):
    yield {"event": "done", "data": "{}"}


@pytest.fixture(autouse=True)
def _reset_sse_starlette_exit_event():
    # sse_starlette caches a single AppStatus.should_exit_event (an anyio
    # Event) at module scope, bound to whichever event loop first triggered
    # an EventSourceResponse. TestClient spins up a fresh event loop per
    # test, so a second SSE-returning test in the same process trips
    # "Event object is bound to a different event loop" inside
    # sse_starlette's own internals -- not a bug in this route. Resetting the
    # cached event before each test is sse_starlette's own documented
    # workaround for this exact cross-test-loop issue.
    import sse_starlette.sse as sse_module
    sse_module.AppStatus.should_exit_event = None
    yield


def test_query_unauthorized():
    response = client.post("/api/query", json={"session_id": "s1", "query": "test"})
    assert response.status_code == 401


@patch("backend.api.routes.query.stream_job_status", new=_fake_stream)
@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_first_use_claims_session(mock_get_session, mock_get, mock_set, mock_dispatch):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    # session_owner:<sid> unclaimed, query_rate:officer_1 unset
    mock_get.return_value = None
    mock_dispatch.return_value = "job_123"

    response = client.post(
        "/api/query",
        json={"session_id": "brand-new-session", "query": "any cases match this MO?"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 200
    # QueryRequest now carries a `language` field (default "en") that the route
    # forwards to dispatch_query_job as its third positional arg.
    mock_dispatch.assert_called_once_with("brand-new-session", "any cases match this MO?", "en")
    # session_owner claim write + rate counter write
    assert mock_set.call_count == 2


@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_cross_officer_session_reuse_blocked(mock_get_session, mock_get, mock_set, mock_dispatch):
    mock_get_session.return_value = {"username": "officer_2", "role": "inspector"}

    def get_side_effect(key):
        if key == "query_rate:officer_2":
            return None
        if key == "session_owner:someone-elses-session":
            return {"value": "officer_1"}
        return None

    mock_get.side_effect = get_side_effect

    response = client.post(
        "/api/query",
        json={"session_id": "someone-elses-session", "query": "status update"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 403
    assert response.json() == {"detail": "This session belongs to a different officer"}
    mock_dispatch.assert_not_called()


@patch("backend.api.routes.query.stream_job_status", new=_fake_stream)
@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_same_owner_reuse_allowed(mock_get_session, mock_get, mock_set, mock_dispatch):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}

    def get_side_effect(key):
        if key == "query_rate:officer_1":
            return None
        if key == "session_owner:my-session":
            return {"value": "officer_1"}
        return None

    mock_get.side_effect = get_side_effect
    mock_dispatch.return_value = "job_456"

    response = client.post(
        "/api/query",
        json={"session_id": "my-session", "query": "follow up question"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 200
    mock_dispatch.assert_called_once()


@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_rate_limit_exceeded(mock_get_session, mock_get, mock_set, mock_dispatch):
    mock_get_session.return_value = {"username": "officer_3", "role": "inspector"}
    # Already at the cap -- rate check must reject before the session-ownership
    # check or dispatch ever run.
    mock_get.return_value = {"value": "30"}

    response = client.post(
        "/api/query",
        json={"session_id": "s-anything", "query": "another one"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 429
    mock_dispatch.assert_not_called()


@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.routes.query.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_unknown_case_scoped_session_rejected(mock_get_session, mock_get, mock_dispatch):
    # "s_" session ids are now first-class: query.py no longer blocks the
    # prefix outright but routes it through the case's collaborator ACL
    # (see _authorize_session). An "s_" id with no session_meta record must
    # still be refused -- 404, before dispatch.
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = None

    response = client.post(
        "/api/query",
        json={"session_id": "s_deadbeef", "query": "anything"},
        headers={"Authorization": "Bearer mocktoken"},
    )

    assert response.status_code == 404
    mock_dispatch.assert_not_called()


@patch("backend.api.routes.query.dispatch_query_job", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_query_rejects_oversized_query_text(mock_get_session, mock_dispatch):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}

    response = client.post(
        "/api/query",
        json={"session_id": "s1", "query": "x" * 2001},
        headers={"Authorization": "Bearer mocktoken"},
    )

    # backend/api/middleware/input_validator.py's dedicated /query-path check
    # (MAX_TEXT_QUERY_LEN = 2000) rejects this with its own 400 at the ASGI
    # layer before the route or Pydantic's max_length=2000 is ever reached.
    assert response.status_code == 400
    mock_dispatch.assert_not_called()
