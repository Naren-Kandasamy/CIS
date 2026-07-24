from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field
from shared.catalyst_client import text_to_speech

router = APIRouter()

# BUG FIX: no max_length -- relied entirely on the global content-length-based
# middleware gate (bypassable via chunked transfer encoding, same class as
# the transcribe.py/ocr.py findings) as the only size guard on synthesis
# input handed to the Zia TTS API.
class TTSRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    language: str = "kn"

@router.post("/api/tts")
async def generate_tts(request: TTSRequest):
    try:
        audio_bytes = await text_to_speech(request.text, request.language)
    except Exception as e:
        # BUG FIX: str(e) on the httpx exception echoed internal details
        # (including the real upstream Zia API URL) straight back to the
        # client, and collapsed every failure -- including client input
        # errors -- into a generic 500. Log the real error server-side and
        # return a generic message instead.
        print(f"[TTS ERROR] text_to_speech failed: {e}")
        raise HTTPException(status_code=502, detail="TTS synthesis failed, please retry")

    # BUG FIX: declared media_type="audio/mpeg" (MP3), but text_to_speech()
    # (shared/catalyst_client.py) returns the Zia TTS endpoint's actual
    # response bytes verbatim, which per the verified model card
    # (Docs/PS1_Voice_Language_Layer_v2.md Section 3.2) is audio/wav, not MP3
    # -- mislabeling the format can make browser <audio> playback fail
    # depending on how strictly the client trusts the Content-Type.
    return Response(content=audio_bytes, media_type="audio/wav")
