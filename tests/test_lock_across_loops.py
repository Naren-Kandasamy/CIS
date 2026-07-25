import asyncio

lock = asyncio.Lock()

async def main():
    async with lock:
        print("Acquired!")

asyncio.run(main())
try:
    asyncio.run(main())
except Exception as e:
    print("ERROR:", type(e), e)
