import os
import asyncio
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test_quickml():
    token = os.getenv("CATALYST_API_TOKEN")
    url = os.getenv("CATALYST_LLM_ENDPOINT")
    
    headers = {
        "Authorization": f"Zoho-oauthtoken {token}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "messages": [
            {"role": "system", "content": "You are a test agent."},
            {"role": "user", "content": "Say hello world."}
        ],
        "model": "Qwen2.5-7B-Instruct",
        "temperature": 0.0
    }
    
    async with httpx.AsyncClient() as client:
        r = await client.post(url, headers=headers, json=payload)
        print(f"Status: {r.status_code}")
        print(f"Response: {r.text[:200]}")

if __name__ == "__main__":
    asyncio.run(test_quickml())
