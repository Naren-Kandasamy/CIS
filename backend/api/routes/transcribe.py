import httpx
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from shared.catalyst_client import transcribe_and_normalize
from backend.api.middleware.input_validator import validate_mime_type, MAX_AUDIO_SIZE_BYTES

router = APIRouter()

# BUG FIX: "audio/webm" was accepted here, but Zia ASR rejects .webm with
# 400 INVALID_FILE_EXTENSION (verified live), so accepting it only let the
# request travel further before failing as an opaque 500. The client now
# encodes WAV in-browser (client/src/lib/wavRecorder.ts) instead of relying
# on MediaRecorder's webm output.
ALLOWED_AUDIO_MIMES = ["audio/wav", "audio/x-wav", "audio/mpeg", "audio/ogg", "audio/flac"]

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
    
    # BUG FIX: the uploaded filename was dropped entirely, so every request
    # reached Zia under transcribe_audio()'s default name. Zia validates the
    # format by extension, so the name has to reflect what was actually sent.
    # Fall back to .wav (what the client encodes) if the name is missing or
    # carries an extension Zia doesn't accept.
    filename = audio.filename or ""
    if not filename.lower().endswith((".wav", ".mp3", ".ogg", ".flac")):
        filename = "recording.wav"

    try:
        transcript = await transcribe_and_normalize(audio_bytes, language, filename=filename)
        return {"transcript": transcript}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except httpx.HTTPStatusError as e:
        # BUG FIX: upstream Zia failures propagated uncaught and surfaced to
        # the officer as a bare 500 with no context (this is what the
        # "Transcription failed: Internal Server Error" in the UI was). Log
        # the real cause server-side, return a clean message.
        print(f"[TRANSCRIBE ERROR] Zia ASR returned {e.response.status_code}: {e.response.text[:300]}")
        raise HTTPException(status_code=502, detail="Transcription service failed, please retry")
