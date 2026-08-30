import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)
AUTH_HEADERS = {"Authorization": "Bearer mocktoken"}

# BUG FIX: these tests never mocked or sent RBAC auth, so every request hit
# RBACMiddleware's 401 before reaching the route at all -- the assertions
# below were never actually exercising the transcribe/translate route logic.
#
# They also used to deep-mock httpx.AsyncClient.post and assert it was called
# exactly once. Both routes now delegate to multi-hop orchestrators in
# shared/catalyst_client.py (ASR -> translate -> LLM phonetic correction for
# transcribe; LLM-backed translate_text), so the single-call assumption and
# the old {"transcript": ...} / {"translated_text": ...} response shapes no
# longer hold. Mock at the orchestrator boundary instead -- the route's own
# job (auth, form binding, error mapping) is what these tests cover.

# Real RIFF/WAVE magic bytes so validate_mime_type's sniff check passes;
# webm is no longer an accepted upload format (see transcribe.py's
# ALLOWED_AUDIO_MIMES -- Zia ASR rejects it, the client encodes WAV now).
DUMMY_WAV = b"RIFF\x00\x00\x00\x00WAVE" + b"dummy audio content"


@patch("backend.api.routes.transcribe.transcribe_and_normalize", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_transcribe_route_success(mock_get_session, mock_transcribe):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_transcribe.return_value = "mocked transcription"

    response = client.post(
        "/api/transcribe",
        headers=AUTH_HEADERS,
        files={"audio": ("test.wav", DUMMY_WAV, "audio/wav")},
        # language is bound via Form(...), matching the real client
        # (App.tsx sends it as a multipart form field, not a query param).
        data={"language": "kn"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "mocked transcription"}
    mock_transcribe.assert_awaited_once()
    # the route must forward the form-bound language + a Zia-acceptable filename
    args, kwargs = mock_transcribe.call_args
    assert args[1] == "kn"


@patch("backend.api.routes.transcribe.transcribe_and_normalize", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_transcribe_route_non_zia_language_degrades(mock_get_session, mock_transcribe):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    # feat/indic-asr change: a non-Zia voice language (e.g. "ta") no longer
    # hard-fails with 400. transcribe_audio() sends it to Zia as "en" (or the
    # ONNX/HF/Whisper cascade handles it), and normalize_transcript_text still
    # cleans the result. The route just returns whatever the orchestrator gives.
    mock_transcribe.return_value = "cleaned tamil-origin query"
    response = client.post(
        "/api/transcribe",
        headers=AUTH_HEADERS,
        files={"audio": ("test.wav", DUMMY_WAV, "audio/wav")},
        data={"language": "ta"},
    )

    assert response.status_code == 200
    assert response.json() == {"transcript": "cleaned tamil-origin query"}
    args, _ = mock_transcribe.call_args
    assert args[1] == "ta"  # route still forwards the declared language verbatim


@patch("backend.api.routes.transcribe.normalize_transcript_text", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_normalize_route(mock_get_session, mock_normalize):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_normalize.return_value = "Show crime details for FIR No. 142 at Belagavi station"
    response = client.post(
        "/api/transcribe/normalize",
        headers=AUTH_HEADERS,
        json={"text": "belagavi station case 142 torisi", "language": "kn-IN"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["normalized_text"] == "Show crime details for FIR No. 142 at Belagavi station"
    assert body["original_text"] == "belagavi station case 142 torisi"
    mock_normalize.assert_awaited_once_with("belagavi station case 142 torisi", source_lang="kn-IN")


@patch("backend.api.routes.transcribe.normalize_transcript_text", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_normalize_route_returns_raw_on_failure(mock_get_session, mock_normalize):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_normalize.side_effect = RuntimeError("LLM down")
    response = client.post(
        "/api/transcribe/normalize",
        headers=AUTH_HEADERS,
        json={"text": "raw transcript", "language": "en-IN"},
    )
    assert response.status_code == 200
    assert response.json()["normalized_text"] == "raw transcript"


@patch("backend.api.routes.translate.translate_text", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_translate_route_success(mock_get_session, mock_translate):
    mock_get_session.return_value = {"username": "officer_1", "role": "inspector"}
    mock_translate.return_value = {"translated_text": "mocked translation", "processing_time": 123}

    response = client.post(
        "/api/translate",
        headers=AUTH_HEADERS,
        json={"text": "namaskara", "source_lang": "kn", "target_lang": "en"},
    )

    assert response.status_code == 200
    assert response.json()["translated_text"] == "mocked translation"
    mock_translate.assert_awaited_once_with("namaskara", "kn", "en")
