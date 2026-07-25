import asyncio
from neo4j import AsyncGraphDatabase

async def main():
    driver = AsyncGraphDatabase.driver("bolt://localhost:7687", auth=("",""))
    await driver.close()
    print("Success")

asyncio.run(main())
asyncio.run(main())
asyncio.run(main())
