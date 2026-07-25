from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer mocktoken"}
INSPECTOR_SESSION = {"username": "officer_1", "role": "inspector"}


def test_tts_unauthorized():
    response = client.post("/api/tts", json={"text": "hello", "language": "kn"})
    assert response.status_code == 401


@patch("backend.api.routes.tts.text_to_speech", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_tts_success_returns_wav(mock_get_session, mock_tts):
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_tts.return_value = b"RIFF....WAVEfmt "

    response = client.post(
        "/api/tts",
        json={"text": "Suspect last seen near the market", "language": "kn"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "audio/wav"
    assert response.content == b"RIFF....WAVEfmt "
    mock_tts.assert_called_once_with("Suspect last seen near the market", "kn")


@patch("backend.api.middleware.rbac.get_session")
def test_tts_rejects_oversized_text(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/tts",
        json={"text": "x" * 2001, "language": "kn"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


@patch("backend.api.middleware.rbac.get_session")
def test_tts_rejects_empty_text(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/tts",
        json={"text": "", "language": "kn"},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 422


@patch("backend.api.routes.tts.text_to_speech", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_tts_upstream_failure_returns_generic_502(mock_get_session, mock_tts):
    # BUG FIX regression coverage: the raw exception (which could contain the
    # real upstream Zia API URL) must never reach the client.
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_tts.side_effect = Exception("connection refused to https://internal-zia-host.example/v1/tts")

    response = client.post(
        "/api/tts",
        json={"text": "hello", "language": "kn"},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 502
    assert "internal-zia-host" not in response.text
    assert response.json()["detail"] == "TTS synthesis failed, please retry"
