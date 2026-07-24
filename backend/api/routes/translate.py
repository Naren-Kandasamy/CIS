from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from shared.catalyst_client import translate_text

router = APIRouter()

# BUG FIX: no max_length on any field, unlike the sibling QueryRequest model
# (backend/api/routes/query.py, max_length=500) -- relied entirely on the
# global content-length-based middleware gate, bypassable via chunked
# transfer encoding, as the only size guard.
class TranslationRequest(BaseModel):
    text: str = Field(max_length=2000)
    source_lang: str = Field(max_length=16)
    target_lang: str = Field(default="en", max_length=16)

@router.post("/api/translate")
async def translate_route(req: TranslationRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text to translate cannot be empty")
    try:
        result = await translate_text(req.text, req.source_lang, req.target_lang)
        # Expected format from model card: {"translated_text": ..., "processing_time": ...}
        return result
    except Exception as e:
        # BUG FIX: str(e) on the httpx exception echoed internal details
        # (including the real upstream Zia API URL/response) straight back to
        # the client. Log the real error server-side and return a generic
        # message instead.
        print(f"[TRANSLATE ERROR] translate_text failed: {e}")
        raise HTTPException(status_code=502, detail="Translation failed, please retry")
