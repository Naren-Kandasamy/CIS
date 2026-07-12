import asyncio
from shared.catalyst_client import nosql_get, _get_nosql_access_token

async def test():
    # We can't list all keys easily without knowing them, 
    # but wait, can we? No, it's key-value.
    pass

asyncio.run(test())
