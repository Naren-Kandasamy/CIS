from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shared.catalyst_client import translate_text

router = APIRouter()

class TranslationRequest(BaseModel):
    text: str
    source_lang: str
    target_lang: str = "en"

@router.post("/api/translate")
async def translate_route(req: TranslationRequest):
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="Text to translate cannot be empty")
    try:
        result = await translate_text(req.text, req.source_lang, req.target_lang)
        # Expected format from model card: {"translated_text": ..., "processing_time": ...}
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Translation failed: {str(e)}")
