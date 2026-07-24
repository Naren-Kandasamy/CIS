import asyncio
import os
from dotenv import load_dotenv, set_key
load_dotenv()
from shared.catalyst_client import _get_nosql_access_token

async def main():
    try:
        fresh_token = await _get_nosql_access_token()
        print("Fresh token:", fresh_token[:10] + "...")
        set_key("/home/nkandasamy/Desktop/CIS/.env", "CATALYST_API_TOKEN", fresh_token)
        print("Successfully updated .env with fresh token!")
    except Exception as e:
        print("Error refreshing token:", e)

asyncio.run(main())
