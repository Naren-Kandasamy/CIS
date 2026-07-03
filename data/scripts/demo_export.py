import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from backend.main import app
from fastapi.testclient import TestClient

client = TestClient(app)

def run_export_demo():
    print("Testing PDF Export Endpoint...")
    
    payload = {
        "query": "Show me robbery cases in Belagavi.",
        "answer": "The system retrieved 2 robbery cases from Belagavi matching your query. Both involved the suspect breaking through the rear window.",
        "evidence": [
            {
                "fir_id": "124/2023",
                "confidence": "high (0.91)",
                "data": {
                    "Date": "2023-10-15",
                    "district": "Belagavi",
                    "crime_type": "Robbery",
                    "narrative": "Complainant Shri Ramesh Kumar states an unknown individual gained entry by breaking the iron grill of the rear window..."
                }
            }
        ]
    }
    
    response = client.post("/api/export/pdf", json=payload)
    
    if response.status_code == 200:
        out_file = "demo_report.pdf"
        with open(out_file, "wb") as f:
            f.write(response.content)
        print(f"✅ PDF Export Successful! Saved to {out_file} ({len(response.content)} bytes)")
    else:
        print(f"❌ PDF Export Failed: {response.status_code} - {response.text}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    run_export_demo()
