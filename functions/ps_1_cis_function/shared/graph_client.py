import asyncio
from neo4j import AsyncGraphDatabase  # neo4j driver works with Memgraph bolt
import os
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

async def get_driver():
    # In a serverless environment where event loops are destroyed per-invocation,
    # global caching of the neo4j driver causes "Task attached to a different loop"
    # because the driver internally caches event-loop-bound connections.
    return AsyncGraphDatabase.driver(
        os.getenv("MEMGRAPH_URI"),
        auth=(os.getenv("MEMGRAPH_USERNAME", ""),
              os.getenv("MEMGRAPH_PASSWORD", ""))
    )

# BUG FIX: mutable default arg `params={}` would accumulate state across calls.
async def run_query(cypher: str, params: dict = None) -> list:
    if params is None:
        params = {}
        
    if os.getenv("LOCAL_MOCK_MODE", "false").lower() == "true":
        if os.getenv("X_ZOHO_CATALYST_LISTEN_PORT"):
            raise EnvironmentError("LOCAL_MOCK_MODE=true must NOT be set in a deployed environment.")
        # Return mock evidence so the LLM can test reasoning logic
        return [{
            "fir_id": "MOCK-FIR-001",
            "crime_no": "123/2023",
            "district": params.get("city", "Unknown City"),
            "crime_type": "Robbery",
            "modus_operandi": "Suspect used a specialized glass cutter to breach the rear window of the house.",
            "narrative": "At 2AM, the suspect approached the rear window. A specialized glass cutter was found at the scene.",
            "date": "2023-11-14",
            "score": 0.95
        }]
        
    driver = await get_driver()
    try:
        async with driver.session() as session:
            result = await session.run(cypher, params)
            return [record.data() async for record in result]
    finally:
        await driver.close()

# BUG FIX: mutable default arg fix, plus execute_write lambda was not async-safe --
# the lambda `lambda tx: tx.run(cypher, params)` returns a coroutine that is never
# awaited inside execute_write. Use session.run() directly inside a write transaction.
async def run_write(cypher: str, params: dict = None):
    if params is None:
        params = {}
    driver = await get_driver()
    try:
        async with driver.session() as session:
            await session.run(cypher, params)
    finally:
        await driver.close()

async def run_write_batch(cypher: str, params_list: list[dict]):
    if not params_list:
        return
    driver = await get_driver()
    try:
        async with driver.session() as session:
            for params in params_list:
                await session.run(cypher, params)
    finally:
        await driver.close()

async def close():
    # In serverless environments, driver is now created and closed per-request
    # so there is no global _driver to close. We keep this function for backwards
    # compatibility with existing scripts.
    pass
