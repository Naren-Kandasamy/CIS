import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        await client.get("https://example.com")
        print("Success")

def handler():
    # If anyio caches something on the thread, doing this twice might fail in older anyio?
    # Actually wait, let's just use the global loop workaround to see if it's safe.
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    _loop.run_until_complete(main())

_loop = None
handler()
handler()
