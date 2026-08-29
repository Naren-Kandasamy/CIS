"""Phase 4/5 backend coverage: the mutable corkboard layout doc
(case_board_layout:{case_id}) and its size caps, plus delete_case cleanup.

Same mocking convention as test_cases.py: TestClient(app) with the NoSQL
helpers and the rbac session lookup patched. get_session is async, so
unittest.mock.patch auto-substitutes an AsyncMock and .return_value works
through the middleware's `await`.
"""
import json
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

_CASE_ID = "c_board001"
_ONE_CARD = {
    "id": "hyp:abc",
    "kind": "hypothesis",
    "refId": "abc",
    "x": 120.0,
    "y": 80.5,
    "w": 250.0,
    "h": 200.0,
    "color": "var(--pin-gold)",
    "rotation": -3.0,
    "text": "shared modus operandi",
    "connections": ["fir:XYZ"],
}


def _case_doc(collaborators=("officer_1",)):
    return {"value": json.dumps({"case_id": _CASE_ID, "collaborators": list(collaborators)})}


# ── auth gate ───────────────────────────────────────────────────────────────

def test_put_board_layout_unauthorized():
    r = client.put(f"/api/cases/{_CASE_ID}/board/layout", json={"cards": []})
    assert r.status_code == 401


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_not_a_collaborator_returns_403(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "outsider", "role": "inspector"}
    mock_get.return_value = _case_doc(collaborators=("officer_1",))

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [_ONE_CARD]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 403
    assert r.json() == {"detail": "Not authorized for this case"}


# ── round trip ──────────────────────────────────────────────────────────────

@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_get_board_layout_empty_when_absent(mock_get_session, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    # first read: case doc (auth); second read: the layout doc -> absent
    mock_get.side_effect = [_case_doc(), None]

    r = client.get(
        f"/api/cases/{_CASE_ID}/board/layout",
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 200
    assert r.json() == {"cards": []}
    mock_set.assert_not_called()


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_then_get_board_layout_round_trip(mock_get_session, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    put = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [_ONE_CARD]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert put.status_code == 200
    assert put.json()["cards"][0]["id"] == "hyp:abc"
    assert put.json()["cards"][0]["connections"] == ["fir:XYZ"]

    # exactly one write, to the layout key, with audit fields
    assert mock_set.call_count == 1
    key, payload = mock_set.call_args[0]
    assert key == f"case_board_layout:{_CASE_ID}"
    doc = json.loads(payload)
    assert doc["updated_by"] == "officer_1"
    assert "updated_at" in doc
    assert doc["cards"][0]["kind"] == "hypothesis"

    # now simulate the stored doc being read back
    mock_get.side_effect = [_case_doc(), {"value": payload}]
    got = client.get(
        f"/api/cases/{_CASE_ID}/board/layout",
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert got.status_code == 200
    assert got.json()["cards"][0]["x"] == 120.0


@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_accepts_empty_and_hex_and_word_colors(mock_get_session, mock_get, mock_set):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    cards = [
        {**_ONE_CARD, "id": "a", "color": "#a9791f"},
        {**_ONE_CARD, "id": "b", "color": "crimson"},
        {**_ONE_CARD, "id": "c", "color": "var(--pin-gold)"},
    ]
    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": cards},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 200
    assert len(r.json()["cards"]) == 3


# ── size / shape caps -> 422 (Pydantic, before the handler) ─────────────────

@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_201_cards(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    cards = [{**_ONE_CARD, "id": f"c{i}"} for i in range(201)]
    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": cards},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_oversized_text(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [{**_ONE_CARD, "text": "x" * 2001}]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_oversized_connections(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [{**_ONE_CARD, "connections": [f"n{i}" for i in range(51)]}]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_bad_kind(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [{**_ONE_CARD, "kind": "sticky"}]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_bad_color(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [{**_ONE_CARD, "color": "not a colour!!"}]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_put_board_layout_rejects_non_numeric_coords(mock_get_session, mock_get):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_get.return_value = _case_doc()

    r = client.put(
        f"/api/cases/{_CASE_ID}/board/layout",
        json={"cards": [{**_ONE_CARD, "x": "left"}]},
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 422


# ── delete_case cleans up the layout + hypotheses-by-case index ─────────────

@patch("backend.api.routes.cases.nosql_delete", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_set", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_delete_case_removes_board_layout_and_hypotheses_index(
    mock_get_session, mock_get, mock_set, mock_delete
):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    case = {"case_id": _CASE_ID, "collaborators": ["officer_1"], "created_by": "officer_1"}
    # reads in order: case doc (auth) -> user_cases:officer_1 (index cleanup)
    # -> case_sessions:{id} (a JSON list of session ids, here empty)
    mock_get.side_effect = [
        {"value": json.dumps(case)},
        {"value": json.dumps([_CASE_ID])},
        {"value": json.dumps([])},
    ]

    r = client.delete(
        f"/api/cases/{_CASE_ID}",
        headers={"Authorization": "Bearer mocktoken"},
    )
    assert r.status_code == 200

    deleted_keys = {call.args[0] for call in mock_delete.call_args_list}
    assert f"case_board_layout:{_CASE_ID}" in deleted_keys
    assert f"hypotheses_by_case:{_CASE_ID}" in deleted_keys
    assert f"case_board:{_CASE_ID}" in deleted_keys
    assert f"case:{_CASE_ID}" in deleted_keys
