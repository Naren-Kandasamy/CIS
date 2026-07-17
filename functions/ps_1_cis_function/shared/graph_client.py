import asyncio
from neo4j import AsyncGraphDatabase  # neo4j driver works with Memgraph bolt
import os

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
        # BUG FIX: X_ZOHO_CATALYST_LISTEN_PORT is AppSail-specific -- this
        # pipeline is also deployed as its own separate Catalyst Function
        # (serverless, no "listen port" concept), where that var is never
        # set. If LOCAL_MOCK_MODE=true were ever accidentally left in a
        # deployed Function's env config, this guard would silently miss it
        # and the Function would serve fabricated mock evidence in
        # production instead of raising. ZC_PROJECT_ID/CATALYST_PROJECT_ID is
        # already used elsewhere (shared/catalyst_client.py) as the
        # deployment-agnostic "real Catalyst credentials are configured"
        # signal -- present in both AppSail and Function environments --
        # check that too, not just the AppSail-only marker.
        if os.getenv("X_ZOHO_CATALYST_LISTEN_PORT") or os.getenv("ZC_PROJECT_ID") or os.getenv("CATALYST_PROJECT_ID"):
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
    # BUG FIX: referenced a global `_driver` that is never defined anywhere
    # in this module -- `global _driver; if _driver:` on a name with no
    # module-level assignment raises NameError on every call, unconditionally
    # (backend/main.py's shutdown lifespan calls this on every app stop). Its
    # original intent (release a shared connection pool at shutdown) no
    # longer applies: get_driver() creates a fresh driver per call, and
    # run_query/run_write already close their own driver in a finally block
    # after every use, so there is no persistent driver left to close here.
    # Kept as a callable no-op rather than removed outright so main.py's
    # shutdown hook doesn't need a matching change.
    pass
