import asyncio
from shared.catalyst_client import kb_search
from dotenv import load_dotenv

load_dotenv("pipeline_function/.env")

async def main():
    try:
        res = await kb_search("What are the details of the recent theft cases in Bangalore?", top_k=10)
        print("RAG results count:", len(res.get("results", [])))
    except Exception as e:
        print("Failed:", e)

asyncio.run(main())
