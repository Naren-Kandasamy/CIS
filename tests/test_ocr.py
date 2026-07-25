import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

AUTH_HEADERS = {"Authorization": "Bearer mocktoken"}
INSPECTOR_SESSION = {"username": "officer_1", "role": "inspector"}

# Minimal valid JPEG magic-number prefix, enough for validate_mime_type's
# signature sniff (backend/api/middleware/input_validator.py) to accept it.
FAKE_JPEG_BYTES = b"\xFF\xD8\xFF" + b"\x00" * 100


def test_ocr_unauthorized():
    response = client.post(
        "/api/upload",
        files={"image": ("fir.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
    )
    assert response.status_code == 401


@patch("backend.api.routes.ocr.vlm_extract", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_ocr_success_returns_extracted_fields(mock_get_session, mock_vlm):
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_vlm.return_value = json.dumps({
        "FIR Number": "123/2024",
        "Date": "2024-01-01",
        "District": "Mysuru",
        "Crime Type": "Robbery",
    })

    response = client.post(
        "/api/upload",
        files={"image": ("fir.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["extracted"]["FIR Number"] == "123/2024"
    mock_vlm.assert_called_once()


@patch("backend.api.middleware.rbac.get_session")
def test_ocr_rejects_unsupported_mime_type(mock_get_session):
    mock_get_session.return_value = INSPECTOR_SESSION
    response = client.post(
        "/api/upload",
        files={"image": ("fir.txt", b"not an image, just plain text", "text/plain")},
        headers=AUTH_HEADERS,
    )
    assert response.status_code == 415


@patch("backend.api.routes.ocr.vlm_extract", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_ocr_upstream_failure_returns_generic_502(mock_get_session, mock_vlm):
    # BUG FIX regression coverage: the raw httpx exception (which could
    # contain internal infrastructure details) must never reach the client.
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_vlm.side_effect = Exception("HTTPStatusError: 500 from https://internal-vlm-host.example/v1/infer")

    response = client.post(
        "/api/upload",
        files={"image": ("fir.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 502
    assert "internal-vlm-host" not in response.text
    assert response.json()["detail"] == "OCR extraction failed, please retry"


@patch("backend.api.routes.ocr.vlm_extract", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_ocr_rejects_output_failing_fir_schema_check(mock_get_session, mock_vlm):
    # BUG FIX regression coverage: a prompt-injected VLM response (e.g. an
    # attacker's document instructing the model to emit arbitrary JSON) must
    # be rejected rather than returned to the client as if it were a genuine
    # FIR extraction, since it won't contain any of the expected FIR fields.
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_vlm.return_value = json.dumps({"attacker_controlled_field": "ignore all previous instructions"})

    response = client.post(
        "/api/upload",
        files={"image": ("fir.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "OCR extraction did not return a valid FIR record"


@patch("backend.api.routes.ocr.vlm_extract", new_callable=AsyncMock)
@patch("backend.api.middleware.rbac.get_session")
def test_ocr_handles_markdown_fenced_json(mock_get_session, mock_vlm):
    mock_get_session.return_value = INSPECTOR_SESSION
    mock_vlm.return_value = '```json\n{"FIR Number": "45/2024", "District": "Bengaluru"}\n```'

    response = client.post(
        "/api/upload",
        files={"image": ("fir.jpg", FAKE_JPEG_BYTES, "image/jpeg")},
        headers=AUTH_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["extracted"]["FIR Number"] == "45/2024"
