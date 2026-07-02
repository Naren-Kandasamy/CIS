import asyncio
from dotenv import load_dotenv
load_dotenv()
from pipeline_function.pipeline.retrieval.executor import run_graph_step

async def main():
    state = {
        "intent": {
            "entities": {
                "locations": ["Belagavi"],
                "crime_types": ["robbery"]
            }
        }
    }
    
    results = await run_graph_step({}, state)
    print("Graph Evidence Retreived:", len(results))
    for res in results:
        print(res)

asyncio.run(main())
