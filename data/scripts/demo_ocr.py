import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def run_ocr_demo(image_path: str):
    print(f"Testing OCR Endpoint with image: {image_path}")
    
    with open(image_path, "rb") as f:
        image_data = f.read()
        
    print("Uploading to /api/ocr...")
    response = client.post(
        "/api/ocr",
        files={"image": ("sample_fir.png", image_data, "image/png")}
    )
    
    if response.status_code == 200:
        print("✅ OCR Extraction Successful!")
        print("-" * 40)
        print(response.json().get("extracted", "No extracted data"))
        print("-" * 40)
    else:
        print(f"❌ OCR Extraction Failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    if len(sys.argv) > 1:
        img_path = sys.argv[1]
    else:
        # Default to the generated image if not provided
        img_path = "/home/nkandasamy/.gemini/antigravity/brain/c8adaddc-8e5a-4f76-800c-d6d111e8126f/sample_fir_1783058517818.png"
        
    run_ocr_demo(img_path)
