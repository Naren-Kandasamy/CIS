import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    try:
        driver = AsyncGraphDatabase.driver("bolt://92.4.84.250:7687", auth=("", ""))
        async with driver.session() as session:
            res = await session.run("MATCH (f:FIR) RETURN DISTINCT f.district LIMIT 10")
            records = [record.data() async for record in res]
            print(f"Districts in Graph:", records)
        await driver.close()
    except Exception as e:
        print("Failed:", e)

asyncio.run(main())
