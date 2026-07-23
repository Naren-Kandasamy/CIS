import asyncio
import sys
from dotenv import load_dotenv
from shared.catalyst_client import kb_search

load_dotenv()

async def main():
    query = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "What are the common MOs in Belagavi?"
    print(f"Querying KB with: '{query}'")
    try:
        results = await kb_search(query)
        print("KB Results:")
        import json
        print(json.dumps(results, indent=2))
    except Exception as e:
        print(f"Error querying KB: {e}")

if __name__ == "__main__":
    asyncio.run(main())
