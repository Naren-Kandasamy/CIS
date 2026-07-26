import asyncio
import traceback
from shared.catalyst_client import kb_search
import os
from dotenv import load_dotenv

load_dotenv("pipeline_function/.env")

# Override with the values from the screenshot
os.environ["ZC_KB_ENDPOINT"] = "https://api.catalyst.zoho.in/quickml/v1/project/45958000000015001/rag/answer"
os.environ["ZC_KB_DOCUMENTS"] = "368200000004002"
os.environ["ZC_ACCESS_TOKEN"] = "1000.17b3f2ae7bd230327b860a5bdbe537d6.58e084bffb80032817610b3d9011ecca"
os.environ["ZC_PROJECT_ID"] = "45958000000015001"

async def main():
    try:
        print("Testing RAG with doc:", os.environ["ZC_KB_DOCUMENTS"])
        res = await kb_search("What are the details of the recent theft cases in Bangalore?", top_k=10)
        print("RAG results count:", len(res.get("results", [])))
        if res.get("results"):
            print("First result:", res["results"][0])
    except Exception as e:
        print("Failed:", type(e).__name__, str(e))
        traceback.print_exc()

asyncio.run(main())
