"""GET /api/graph and GET /api/cases/{id}/graph — the entity relation network
views. NoSQL, the graph DB and the hypothesis index are all mocked; the point
is the seed-FIR gathering, the Cytoscape element assembly, and the cross-case
`shared` flag.
"""
import json
from unittest.mock import patch, AsyncMock

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)

_FIR_A = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
_FIR_B = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


def _pins(fir_ids):
    return {"value": json.dumps([
        {"content_type": "citation", "content": {"fir_id": f}} for f in fir_ids
    ])}


def _fir_rows(ids):
    return [
        {"fid": f, "crime_no": f"CR-{i}", "crime_type": "Theft", "district": "Belagavi", "date": "2024-01-0" + str(i + 1)}
        for i, f in enumerate(ids)
    ]


def test_global_graph_unauthorized():
    assert client.get("/api/graph").status_code == 401


@patch("backend.api.routes.graph.run_query", new_callable=AsyncMock)
@patch("backend.api.routes.graph.list_hypotheses_by_case", new_callable=AsyncMock)
@patch("backend.api.routes.graph.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_global_graph_flags_accused_across_two_cases(
    mock_session, mock_get, mock_hyps, mock_run
):
    mock_session.return_value = {"username": "dysp1", "role": "inspector"}
    mock_hyps.return_value = []

    # user_cases -> [cA, cB]; then case_board for cA (FIR_A), case_board for cB (FIR_B)
    def _get(key):
        if key == "user_cases:dysp1":
            return {"value": json.dumps(["cA", "cB"])}
        if key == "case_board:cA":
            return _pins([_FIR_A])
        if key == "case_board:cB":
            return _pins([_FIR_B])
        return None

    mock_get.side_effect = _get

    # graph DB: ACC-1 is accused in BOTH firs (spans cA and cB); ACC-2 only in FIR_A
    def _run(cypher, params=None):
        if "ACCUSED_IN" in cypher:
            return [
                {"aid": "ACC-1", "fid": _FIR_A},
                {"aid": "ACC-1", "fid": _FIR_B},
                {"aid": "ACC-2", "fid": _FIR_A},
            ]
        if "VICTIM_IN" in cypher:
            return []
        return _fir_rows([_FIR_A, _FIR_B])

    mock_run.side_effect = _run

    r = client.get("/api/graph", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    body = r.json()
    assert body["case_count"] == 2
    assert body["seed_fir_count"] == 2
    assert body["shared_accused_count"] == 1

    nodes = {e["data"]["id"]: e for e in body["elements"] if "source" not in e["data"]}
    assert nodes["ACC-1"]["data"]["shared"] is True
    assert nodes["ACC-1"]["data"]["caseCount"] == 2
    assert nodes["ACC-1"]["data"]["firCount"] == 2
    assert "shared" in nodes["ACC-1"]["classes"]
    assert nodes["ACC-2"]["data"]["shared"] is False
    # two FIR nodes + one location + a district edge each
    assert nodes[_FIR_A]["data"]["type"] == "fir"
    assert any(e["data"].get("id") == "loc::Belagavi" for e in body["elements"])


@patch("backend.api.routes.graph.run_query", new_callable=AsyncMock)
@patch("backend.api.routes.graph.list_hypotheses_by_case", new_callable=AsyncMock)
@patch("backend.api.routes.graph.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_global_graph_degrades_when_graph_db_down(
    mock_session, mock_get, mock_hyps, mock_run
):
    mock_session.return_value = {"username": "dysp1", "role": "inspector"}
    mock_hyps.return_value = []
    mock_get.side_effect = lambda k: {"value": json.dumps(["cA"])} if k == "user_cases:dysp1" else _pins([_FIR_A])
    mock_run.side_effect = RuntimeError("bolt connection refused")

    r = client.get("/api/graph", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    assert r.json() == {"elements": [], "degraded": True, "reason": "bolt connection refused"}


@patch("backend.api.routes.graph.run_query", new_callable=AsyncMock)
@patch("backend.api.routes.graph.list_hypotheses_by_case", new_callable=AsyncMock)
@patch("backend.api.routes.graph.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_case_graph_requires_collaborator(
    mock_session, mock_cases_get, mock_graph_get, mock_hyps, mock_run
):
    mock_session.return_value = {"username": "outsider", "role": "inspector"}
    # _require_collaborator reads case:{id}; outsider is not in collaborators
    mock_cases_get.return_value = {"value": json.dumps({"case_id": "cX", "collaborators": ["dysp1"]})}

    r = client.get("/api/cases/cX/graph", headers={"Authorization": "Bearer t"})
    assert r.status_code == 403
    mock_run.assert_not_called()


@patch("backend.api.routes.graph.run_query", new_callable=AsyncMock)
@patch("backend.api.routes.graph.list_hypotheses_by_case", new_callable=AsyncMock)
@patch("backend.api.routes.graph.nosql_get", new_callable=AsyncMock)
@patch("backend.api.routes.cases.nosql_get", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_case_graph_builds_from_pins(
    mock_session, mock_cases_get, mock_graph_get, mock_hyps, mock_run
):
    mock_session.return_value = {"username": "dysp1", "role": "inspector"}
    mock_cases_get.return_value = {"value": json.dumps({"case_id": "cX", "collaborators": ["dysp1"]})}
    mock_hyps.return_value = []
    mock_graph_get.side_effect = lambda k: _pins([_FIR_A]) if k == "case_board:cX" else None

    def _run(cypher, params=None):
        if "ACCUSED_IN" in cypher:
            return [{"aid": "ACC-9", "fid": _FIR_A}]
        if "VICTIM_IN" in cypher:
            return [{"vid": "VIC-3", "fid": _FIR_A}]
        return _fir_rows([_FIR_A])

    mock_run.side_effect = _run

    r = client.get("/api/cases/cX/graph", headers={"Authorization": "Bearer t"})
    assert r.status_code == 200
    body = r.json()
    assert body["seed_fir_count"] == 1
    types = {e["data"].get("type") for e in body["elements"] if "source" not in e["data"]}
    assert {"fir", "person", "location", "victim"} <= types
    # per-case view carries no cross-case flags
    acc = next(e for e in body["elements"] if e["data"].get("id") == "ACC-9")
    assert "caseCount" not in acc["data"]
    assert "shared" not in acc["data"]
