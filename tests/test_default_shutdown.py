import asyncio

async def main():
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, lambda: 1)  # Initialize default executor
    await loop.shutdown_default_executor()
    await loop.run_in_executor(None, lambda: 2)

asyncio.run(main())
