import asyncio
from dotenv import load_dotenv
load_dotenv("pipeline_function/.env")
from pipeline_function.pipeline.query_understanding.dag_planner import build_dag

async def main():
    intent = {
        "intent_type": "search_cases",
        "entities": {
            "city": "Bangalore",
            "crime_type": ["theft"]
        }
    }
    plan = await build_dag(intent)
    print("Plan:", plan)

asyncio.run(main())
