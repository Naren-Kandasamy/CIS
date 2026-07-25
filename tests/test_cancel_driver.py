import asyncio
from neo4j import AsyncGraphDatabase

async def dummy_server():
    server = await asyncio.start_server(lambda r, w: None, '127.0.0.1', 7687)
    async with server:
        await server.serve_forever()

async def run_query():
    driver = AsyncGraphDatabase.driver("bolt://127.0.0.1:7687", auth=("",""))
    try:
        async with driver.session() as session:
            result = await session.run("CALL db.sleep(2000)")
            return [record.data() async for record in result]
    finally:
        await driver.close()

async def main():
    server_task = asyncio.create_task(dummy_server())
    await asyncio.sleep(0.1) # wait for server to start
    try:
        await asyncio.wait_for(run_query(), timeout=0.5)
    except asyncio.TimeoutError:
        print("Timeout caught")
    server_task.cancel()
        
try:
    asyncio.run(main())
    asyncio.run(main())
except Exception as e:
    print("ERROR:", type(e), e)
