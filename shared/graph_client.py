import asyncio
from neo4j import AsyncGraphDatabase  # neo4j driver works with Memgraph bolt
import os

_driver = None
_driver_lock = asyncio.Lock()

async def get_driver():
    global _driver
    if _driver is None:
        async with _driver_lock:
            if _driver is None:
                _driver = AsyncGraphDatabase.driver(
                    os.getenv("MEMGRAPH_URI"),
                    auth=(os.getenv("MEMGRAPH_USERNAME", ""),
                          os.getenv("MEMGRAPH_PASSWORD", ""))
                )
    return _driver

# BUG FIX: mutable default arg `params={}` would accumulate state across calls.
async def run_query(cypher: str, params: dict = None) -> list:
    if params is None:
        params = {}
        
    if os.getenv("LOCAL_MOCK_MODE", "false").lower() == "true":
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
    async with driver.session() as session:
        result = await session.run(cypher, params)
        return [record.data() async for record in result]

# BUG FIX: mutable default arg fix, plus execute_write lambda was not async-safe --
# the lambda `lambda tx: tx.run(cypher, params)` returns a coroutine that is never
# awaited inside execute_write. Use session.run() directly inside a write transaction.
async def run_write(cypher: str, params: dict = None):
    if params is None:
        params = {}
    driver = await get_driver()
    async with driver.session() as session:
        await session.run(cypher, params)

async def close():
    global _driver
    if _driver:
        await _driver.close()
        _driver = None
