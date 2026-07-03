import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def run_tts_demo(text: str):
    print(f"Testing TTS Endpoint with text: '{text}'")
    
    print("Posting to /api/tts...")
    response = client.post(
        "/api/tts",
        json={"text": text, "language": "en"}
    )
    
    if response.status_code == 200:
        out_file = "demo_tts_output.mp3"
        with open(out_file, "wb") as f:
            f.write(response.content)
        print(f"✅ TTS Successful! Audio saved to {out_file} ({len(response.content)} bytes)")
    else:
        print(f"❌ TTS Failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    sample_text = "The system successfully retrieved evidence for your query. Accused Suresh is linked to 3 prior robbery cases in Belagavi."
    run_tts_demo(sample_text)
