import asyncio
from shared.catalyst_client import nosql_get, nosql_set, nosql_delete
import json
import logging

async def test():
    key = "test_delete_key_123"
    print("Setting...")
    await nosql_set(key, json.dumps({"hello": "world"}))
    
    print("Getting...")
    val1 = await nosql_get(key)
    print("Val1:", val1)
    
    print("Deleting...")
    await nosql_delete(key)
    
    print("Getting again...")
    val2 = await nosql_get(key)
    print("Val2:", val2)

if __name__ == "__main__":
    asyncio.run(test())
