import httpx
import os
from dotenv import load_dotenv

load_dotenv()
token = os.getenv("CATALYST_API_TOKEN")

headers = {
    "Authorization": f"Zoho-oauthtoken {token}",
    "CATALYST-ORG": "60075634347",
    "Content-Type": "application/json"
}

url = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate"
data = {"source_language": "en", "target_language": "kn", "text": "This is a test"}

r = httpx.post(url, headers=headers, json=data)
print(f"Status: {r.status_code}")
print(f"Body: {r.text}")
