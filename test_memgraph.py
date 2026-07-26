import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    try:
        driver = AsyncGraphDatabase.driver("bolt://92.4.84.250:7687", auth=("", ""))
        async with driver.session() as session:
            res = await session.run("MATCH (f:FIR) RETURN count(f) as count")
            records = [record.data() async for record in res]
            print("Connected! Graph count:", records)
        await driver.close()
    except Exception as e:
        print("Failed:", type(e).__name__, str(e))

asyncio.run(main())
