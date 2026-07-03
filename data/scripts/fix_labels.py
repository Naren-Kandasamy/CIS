import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from shared.graph_client import run_write, close

async def main():
    try:
        print("Migrating labels...")
        await run_write("""
        MATCH (p:Person)-[:ACCUSED_IN]->()
        SET p:Accused
        REMOVE p:Person
        """)
        await run_write("""
        MATCH (p:Person)-[:VICTIM_IN]->()
        SET p:Victim
        REMOVE p:Person
        """)
        print("✅ Labels migrated.")
    finally:
        await close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
