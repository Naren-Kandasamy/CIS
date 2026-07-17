from fastapi import APIRouter, UploadFile, File, HTTPException
from shared.catalyst_client import transcribe_audio
from backend.api.middleware.input_validator import validate_mime_type, MAX_AUDIO_SIZE_BYTES

router = APIRouter()

ALLOWED_AUDIO_MIMES = ["audio/webm", "audio/mpeg", "audio/wav", "audio/ogg"]

@router.post("/api/transcribe")
async def transcribe_route(audio: UploadFile = File(...), language: str = "kn"):
    audio_bytes = await audio.read()
    if len(audio_bytes) > MAX_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Audio file exceeds 5MB limit")
    if not validate_mime_type(audio_bytes, ALLOWED_AUDIO_MIMES):
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    transcript = await transcribe_audio(audio_bytes, language)
    return {"transcript": transcript}
