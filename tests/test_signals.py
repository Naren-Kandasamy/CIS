import asyncio
import httpx
import os
import json
from shared.catalyst_client import _nosql_headers

url = 'https://api.catalyst.zoho.in/baas/v1/project/45958000000015001/signal/ps1querypublisher/query_job/publish'

async def test():
    headers = await _nosql_headers()
    # auth headers actually require 'Authorization': 'Zoho-oauthtoken ...'
    auth_header = headers.get('Authorization')
    
    async with httpx.AsyncClient(timeout=10) as client:
        # without auth
        try:
            r1 = await client.post(url, json={"job_id": "test", "session_id": "test", "query": "test"})
            print('Without Auth:', r1.status_code, r1.text)
        except Exception as e: print("r1 error", e)

        # with auth
        try:
            r2 = await client.post(url, headers={'Authorization': auth_header}, json={"job_id": "test", "session_id": "test", "query": "test"})
            print('With Auth:', r2.status_code, r2.text)
        except Exception as e: print("r2 error", e)

asyncio.run(test())
