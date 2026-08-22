import asyncio
import json
import os
from shared.catalyst_client import nosql_set, nosql_get, _nosql_request
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def main():
    try:
        # Create a payload of 40KB
        data = "a" * 40000
        print("Testing 40KB write...")
        await nosql_set("test_size", data)
        print("40KB write successful")
    except Exception as e:
        print(f"40KB write failed: {e}")

    try:
        # Create a payload of 100KB
        data = "a" * 100000
        print("Testing 100KB write...")
        await nosql_set("test_size", data)
        print("100KB write successful")
    except Exception as e:
        print(f"100KB write failed: {e}")

asyncio.run(main())
