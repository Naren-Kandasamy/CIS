import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from dotenv import load_dotenv
load_dotenv()

from shared.catalyst_client import nosql_get
import httpx

async def main():
    try:
        print("Attempting to fetch user:dysp1 from NoSQL...")
        res = await nosql_get("user:dysp1")
        print("Success!", res)
    except httpx.HTTPStatusError as e:
        print("HTTP Error:", e.response.status_code)
        print("Error Body:", e.response.text)
    except Exception as e:
        print("Other Error:", e)

if __name__ == "__main__":
    asyncio.run(main())
