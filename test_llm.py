import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_endpoint():
    token = os.getenv("CATALYST_API_TOKEN")
    if not token:
        raise EnvironmentError("CATALYST_API_TOKEN is not set")
    url = "https://api.catalyst.zoho.in/quickml/v1/project/45958000000015001/glm/chat"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Zoho-oauthtoken {token}"
    }
    
    payload = {
        "model": "crm-di-glm47b_30b_it",
        "messages": [
            {
                "role": "user",
                "content": "What's the weather like in Paris today?"
            }
        ]
    }
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=headers, json=payload, timeout=30.0)
            print(f"Status Code: {r.status_code}")
            print(f"Response: {r.text}")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(test_endpoint())
