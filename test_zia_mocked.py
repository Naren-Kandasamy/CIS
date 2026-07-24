import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
import httpx
from backend.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer mocktoken"}

# BUG FIX: these tests never mocked or sent RBAC auth, so every request hit
# RBACMiddleware's 401 before reaching the route at all -- the assertions
# below were never actually exercising the transcribe/translate route logic.


@patch("backend.api.middleware.rbac.get_session")
def test_transcribe_route_success(mock_get_session, mocker):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    # Mock the internal HTTPX call to Zoho
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "mocked transcription"}

    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)

    # Send a dummy webm file (can be just text bytes)
    # Real WebM magic bytes so validate_mime_type's sniff check passes.
    dummy_audio = b"\x1A\x45\xDF\xA3" + b"dummy audio content"
    response = client.post(
        "/api/transcribe?language=kn",
        headers=AUTH_HEADERS,
        files={"audio": ("test.webm", dummy_audio, "audio/webm")}
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "mocked transcription"}
    mock_post.assert_called_once()


@patch("backend.api.middleware.rbac.get_session")
def test_transcribe_route_unsupported_language(mock_get_session):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    # If frontend sends language="ta" (Tamil), it should throw HTTP 400
    # Real WebM magic bytes so validate_mime_type's sniff check passes.
    dummy_audio = b"\x1A\x45\xDF\xA3" + b"dummy audio content"
    response = client.post(
        "/api/transcribe?language=ta",
        headers=AUTH_HEADERS,
        files={"audio": ("test.webm", dummy_audio, "audio/webm")}
    )

    # The orchestrator throws ValueError which is caught and returned as 400
    assert response.status_code == 400
    assert "Zia ASR does not support 'ta'" in response.json()["detail"]


@patch("backend.api.middleware.rbac.get_session")
def test_translate_route_success(mock_get_session, mocker):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"translated_text": "mocked translation", "processing_time": 123}

    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)

    response = client.post(
        "/api/translate",
        headers=AUTH_HEADERS,
        json={"text": "namaskara", "source_lang": "kn", "target_lang": "en"}
    )

    assert response.status_code == 200
    assert response.json()["translated_text"] == "mocked translation"
    mock_post.assert_called_once()
