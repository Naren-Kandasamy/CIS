import asyncio
import json
import os
from shared.catalyst_client import _nosql_request
from dotenv import load_dotenv

load_dotenv("backend/.env")

async def main():
    resp = await _nosql_request("POST", "/item/fetch", {"keys": [{"item_key": {"S": "session:"}}]}) # Wait, /item/fetch needs exact keys.
    # To get all, we probably need ZTSQL or something if it's available, but we can just use the job history to find the session ID.
    # Let's get the latest jobs from the backend logs!
