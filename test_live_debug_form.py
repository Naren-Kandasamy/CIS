import asyncio
import httpx
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import _zia_headers

async def main():
    try:
        url = "https://api.catalyst.zoho.in/quickml/api/v1/models/zia/translate"
        # Try sending as multipart/form-data
        data = {"source_language": "en", "target_language": "kn", "text": "This is a test."}
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=_zia_headers(), data=data, timeout=15.0)
            print("Status:", r.status_code)
            print("Response:", r.text)
    except Exception as e:
        print("Failed:", e)

if __name__ == "__main__":
    asyncio.run(main())
