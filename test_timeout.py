import asyncio
from neo4j import AsyncGraphDatabase

async def execute_with_timeout(coro, timeout):
    try:
        return await asyncio.wait_for(coro, timeout)
    except asyncio.TimeoutError:
        print("Timeout caught")
        return None
    except Exception as e:
        print(f"Exception: {e}")
        return None

async def run_query():
    driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("",""))
    try:
        async with driver.session() as session:
            await asyncio.sleep(2)  # Simulating long query
            return ["result"]
    finally:
        await driver.close()

async def main():
    tasks = [
        execute_with_timeout(run_query(), 0.5), # This will timeout
        execute_with_timeout(run_query(), 3.0), # This will succeed
    ]
    results = await asyncio.gather(*tasks)
    print("Results:", results)

asyncio.run(main())
