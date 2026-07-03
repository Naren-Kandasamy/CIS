from fastapi import APIRouter, UploadFile, File, HTTPException
from shared.catalyst_client import vlm_extract
from backend.api.middleware.input_validator import validate_mime_type

router = APIRouter()

ALLOWED_IMAGE_MIMES = ["image/jpeg", "image/png", "image/webp"]

@router.post("/api/ocr")
async def extract_ocr(image: UploadFile = File(...)):
    image_bytes = await image.read()
    if not validate_mime_type(image_bytes, ALLOWED_IMAGE_MIMES):
        raise HTTPException(status_code=415, detail="Unsupported image format")
        
    system = "You are an AI trained to extract precise structural data from police FIR documents. Do not hallucinate. Output exactly as requested."
    prompt = "Extract all structured fields from this FIR document including FIR Number, Date, District, Crime Type, Modus Operandi (MO), Accused Details, and Victim Details. Return as a clean JSON object."
    
    try:
        result = await vlm_extract(image_bytes, prompt, system)
        return {"extracted": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")
