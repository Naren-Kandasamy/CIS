import pytest
from fastapi.testclient import TestClient
import httpx
from backend.main import app

client = TestClient(app)

def test_transcribe_route_success(mocker):
    # Mock the internal HTTPX call to Zoho
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"transcript": "mocked transcription"}
    
    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)
    
    # Send a dummy webm file (can be just text bytes)
    dummy_audio = b"dummy audio content"
    response = client.post(
        "/api/transcribe?language=kn",
        files={"audio": ("test.webm", dummy_audio, "audio/webm")}
    )
    
    assert response.status_code == 200
    assert response.json() == {"transcript": "mocked transcription"}
    mock_post.assert_called_once()

def test_transcribe_route_unsupported_language():
    # If frontend sends language="ta" (Tamil), it should throw HTTP 400
    dummy_audio = b"dummy audio content"
    response = client.post(
        "/api/transcribe?language=ta",
        files={"audio": ("test.webm", dummy_audio, "audio/webm")}
    )
    
    # The orchestrator throws ValueError which is caught and returned as 400
    assert response.status_code == 400
    assert "Zia ASR does not support 'ta'" in response.json()["detail"]

def test_translate_route_success(mocker):
    mock_response = mocker.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"translated_text": "mocked translation", "processing_time": 123}
    
    mock_post = mocker.patch("httpx.AsyncClient.post", return_value=mock_response)
    
    response = client.post(
        "/api/translate",
        json={"text": "namaskara", "source_lang": "kn", "target_lang": "en"}
    )
    
    assert response.status_code == 200
    assert response.json()["translated_text"] == "mocked translation"
    mock_post.assert_called_once()
