from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer mocktoken"}
INSPECTOR_SESSION = {"username": "officer_1", "role": "inspector"}


def test_export_unauthorized_with_no_session():
    response = client.post(
        "/api/export/pdf",
        json={"query": "ok", "answer": "ok", "evidence": []},
    )
    assert response.status_code == 401


@patch("backend.api.middleware.rbac.get_session")
def test_export_insufficient_rank_rejected(mock_get_session):
    # ROUTE_MIN_ROLE requires sub_inspector or higher; constable must be
    # rejected by RBACMiddleware before the route body ever runs.
    mock_get_session.return_value = {"username": "constable_1", "role": "constable"}
    response = client.post(
        "/api/export/pdf",
        json={"query": "ok", "answer": "ok", "evidence": []},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 403


@patch("backend.api.middleware.rbac.get_session")
def test_export_rejects_oversized_query(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/export/pdf",
        json={"query": "x" * 2001, "answer": "ok", "evidence": []},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


@patch("backend.api.middleware.rbac.get_session")
def test_export_rejects_oversized_answer(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/export/pdf",
        json={"query": "ok", "answer": "x" * 20001, "evidence": []},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


@patch("backend.api.middleware.rbac.get_session")
def test_export_rejects_too_many_evidence_items(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/export/pdf",
        json={"query": "ok", "answer": "ok", "evidence": [{"fir_id": "F1"}] * 51},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


@patch("backend.api.middleware.rbac.get_session")
def test_export_rejects_malformed_evidence_item(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    # "data" missing entirely -- report.html does item.data.get(...), which
    # raises inside template.render() for a dict lacking that key. Must
    # surface as a clean 400, not an unhandled 500.
    with patch("backend.api.routes.export.HTML", MagicMock()):
        response = client.post(
            "/api/export/pdf",
            json={"query": "ok", "answer": "ok", "evidence": [{"fir_id": "F1"}]},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 400


@patch("backend.api.middleware.rbac.get_session")
def test_export_returns_500_when_weasyprint_unavailable(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    with patch("backend.api.routes.export.HTML", None):
        response = client.post(
            "/api/export/pdf",
            json={"query": "ok", "answer": "ok", "evidence": []},
            headers=AUTH_HEADERS,
        )
    assert response.status_code == 500
    assert "WeasyPrint" in response.json()["detail"]


@patch("backend.api.middleware.rbac.get_session")
def test_export_escapes_html_injection_and_preserves_linebreaks(mock_get_session):
    # BUG FIX regression coverage: query/answer/evidence are client-supplied
    # and must never reach WeasyPrint as raw, unescaped HTML (injection), but
    # the answer's intentional \n -> <br> conversion must still produce real
    # line breaks, not literal "&lt;br&gt;" text (see report.html nl2br fix).
    mock_get_session.return_value = INSPECTOR_SESSION
    captured = {}

    def fake_html(string, url_fetcher=None):
        captured["html"] = string
        mock = MagicMock()
        mock.write_pdf.return_value = b"%PDF-fake"
        return mock

    with patch("backend.api.routes.export.HTML", side_effect=fake_html):
        response = client.post(
            "/api/export/pdf",
            json={
                "query": "<img src=x onerror=alert(1)>",
                "answer": "line one\nline two<script>alert(1)</script>",
                "evidence": [
                    {
                        "fir_id": "<b>FIR1</b>",
                        "confidence": 0.9,
                        "data": {"Date": "2024", "district": "X", "crime_type": "Y", "narrative": "n"},
                    }
                ],
            },
            headers=AUTH_HEADERS,
        )

    assert response.status_code == 200
    html_out = captured["html"]
    # The raw tags must never survive un-neutralized -- markupsafe escaping
    # turns "<" / ">" into entities, so "<script>" and a literal "<img...>"
    # tag can never appear, even though the harmless inner text
    # ("onerror=alert(1)") still shows up as escaped, inert text.
    assert "<script>" not in html_out
    assert "<img" not in html_out
    assert "&lt;script&gt;" in html_out
    assert "&lt;img src=x onerror=alert(1)&gt;" in html_out
    assert "line one<br>line two" in html_out


def test_export_url_fetcher_blocks_external_fetch():
    from backend.api.routes.export import _no_external_fetch
    import pytest

    with pytest.raises(ValueError):
        _no_external_fetch("http://internal-host/secret")
    with pytest.raises(ValueError):
        _no_external_fetch("file:///etc/passwd")
