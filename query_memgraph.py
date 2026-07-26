import asyncio
from shared.catalyst_client import graph_query
from dotenv import load_dotenv

load_dotenv("pipeline_function/.env")

async def main():
    q = "MATCH (f:FIR) WHERE toLower(f.district) CONTAINS 'bangalore' RETURN f LIMIT 2"
    res = await graph_query(q)
    print("Graph Results:", res)
    
    q2 = "MATCH (f:FIR) RETURN count(f) as count"
    res2 = await graph_query(q2)
    print("Total FIRs in Graph:", res2)

asyncio.run(main())
