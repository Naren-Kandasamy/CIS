import asyncio
import httpx
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import _headers

async def main():
    # URL 1: /datastore/query
    url = "https://api.catalyst.zoho.in/baas/v1/project/45958000000015001/datastore/query"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url, headers=_headers(), json={"query": "SELECT * FROM cases LIMIT 1"}, timeout=10.0)
            print("Datastore/Query Status:", r.status_code)
            print("Response:", r.text)
    except Exception as e:
        print("Error:", repr(e))

    # URL 2: /query
    url2 = "https://api.catalyst.zoho.in/baas/v1/project/45958000000015001/query"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url2, headers=_headers(), json={"query": "SELECT * FROM cases LIMIT 1"}, timeout=10.0)
            print("Query Status:", r.status_code)
            print("Response:", r.text)
    except Exception as e:
        print("Error:", repr(e))
        
    url_kb = "https://api.catalyst.zoho.in/quickml/v1/project/45958000000015001/knowledgebase/search"
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(url_kb, headers=_headers(), json={"query": "test"}, timeout=10.0)
            print("KB Status:", r.status_code)
            print("KB Response:", r.text)
    except Exception as e:
        print("KB Error:", repr(e))

asyncio.run(main())
