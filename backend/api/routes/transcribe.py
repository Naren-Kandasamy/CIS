from fastapi import APIRouter, UploadFile, File
from shared.catalyst_client import transcribe_audio

router = APIRouter()

@router.post("/api/transcribe")
async def transcribe_route(audio: UploadFile = File(...), language: str = "kn"):
    audio_bytes = await audio.read()
    transcript = await transcribe_audio(audio_bytes, language)
    return {"transcript": transcript}
