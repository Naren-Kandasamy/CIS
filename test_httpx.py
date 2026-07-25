import asyncio
import httpx

async def fetch():
    async with httpx.AsyncClient() as client:
        r = await client.get("https://google.com")
        print(r.status_code)

async def main():
    await fetch()

asyncio.run(main())
asyncio.run(main())
asyncio.run(main())
