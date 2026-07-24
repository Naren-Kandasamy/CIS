import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

from shared.catalyst_client import kb_search
from dotenv import load_dotenv

load_dotenv()

async def main():
    print("Testing Catalyst KB RAG endpoint...")
    query = "robbery"
    print(f"Query: {query}")
    
    try:
        results = await kb_search(query)
        print("\nResults:")
        import json
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == '__main__':
    asyncio.run(main())
