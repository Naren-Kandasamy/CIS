from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from shared.catalyst_client import text_to_speech

router = APIRouter()

class TTSRequest(BaseModel):
    text: str
    language: str = "kn"

@router.post("/api/tts")
async def generate_tts(request: TTSRequest):
    if not request.text:
        raise HTTPException(status_code=400, detail="Text is required")
        
    try:
        audio_bytes = await text_to_speech(request.text, request.language)
        return Response(content=audio_bytes, media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS failed: {str(e)}")
