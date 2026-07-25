import asyncio
import concurrent.futures

async def main():
    pool = concurrent.futures.ThreadPoolExecutor()
    pool.shutdown(wait=False)
    pool.submit(lambda: None)

asyncio.run(main())
