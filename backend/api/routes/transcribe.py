from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from shared.catalyst_client import transcribe_and_normalize
from backend.api.middleware.input_validator import validate_mime_type, MAX_AUDIO_SIZE_BYTES

router = APIRouter()

ALLOWED_AUDIO_MIMES = ["audio/webm", "audio/mpeg", "audio/wav", "audio/ogg"]

@router.post("/api/transcribe")
async def transcribe_route(audio: UploadFile = File(...), language: str = Form("kn")):
    # BUG FIX: `language: str = "kn"` (no Form() wrapper) bound from the URL
    # query string, not the multipart form body -- but the real client
    # (App.tsx) sends it as formData.append('language', ...), a form field.
    # The server-side value was therefore always silently "kn" regardless of
    # what the client sent; harmless only because the client currently also
    # hardcodes "kn", so both sides happened to agree by coincidence. This
    # would silently break the moment a language selector is added.
    # BUG FIX: the 5MB limit was enforced only after the full body was
    # already buffered into memory via .read() (no cap) -- and the only
    # earlier guard (InputValidationMiddleware's Content-Length check) can be
    # bypassed with chunked transfer encoding that omits Content-Length.
    # Capping the read itself means the server never buffers more than the
    # limit regardless of what Content-Length was (or wasn't) sent.
    audio_bytes = await audio.read(MAX_AUDIO_SIZE_BYTES + 1)
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 5MB limit")
    if not validate_mime_type(audio_bytes, ALLOWED_AUDIO_MIMES):
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    
    try:
        transcript = await transcribe_and_normalize(audio_bytes, language)
        return {"transcript": transcript}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
