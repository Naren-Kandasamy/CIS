import httpx
import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_endpoint():
    token = os.getenv("CATALYST_ACCESS_TOKEN", "1000.e30d5f19907c5f9ce57254ec9072b10b.56682135cc7086a16621cefd15147cd4")
    url = "https://api.catalyst.zoho.in/quickml/v1/project/45958000000015001/glm/chat"
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
        "CATALYST-ORG": "60075634347"
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
