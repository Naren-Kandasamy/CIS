import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from shared.graph_client import run_query, close

async def main():
    try:
        res1 = await run_query("MATCH (n) RETURN labels(n) as label, count(n) as count")
        print("Node counts by label:")
        for r in res1:
            print(f" - {r['label']}: {r['count']}")
            
        res2 = await run_query("MATCH (n:Accused) RETURN n.id LIMIT 5")
        print("\nSample Accused IDs:")
        for r in res2:
            print(f" - {r['n.id']}")
            
    finally:
        await close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
