import asyncio
from neo4j import AsyncGraphDatabase  # neo4j driver works with Memgraph bolt
import os

_driver = None

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

async def close():
    """No-op in the current per-invocation driver pattern.
    
    This function exists so callers (tests, lifespan shutdown) can call close()
    without needing to know whether a global driver is cached. In serverless
    environments (Catalyst Functions), a global cached driver would carry a
    stale event-loop reference across invocations and raise
    'Task attached to a different loop'. The pattern here creates a fresh driver
    per call and closes it in the finally block of run_query/run_write instead.
    """
    # _driver is module-level None and is never set; close() is intentionally a
    # no-op. Do not add caching here without also adding the loop-staleness guard
    # documented in shared/catalyst_client.py's get_lock().
    pass
