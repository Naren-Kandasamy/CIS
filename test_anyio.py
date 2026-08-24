import asyncio
import httpx

async def main():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://example.com")
        print(r.status_code)

def handler():
    asyncio.run(main())

handler()
handler()
