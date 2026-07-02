import asyncio
from dotenv import load_dotenv
load_dotenv()
from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline

async def mock_callback(job_id, status, result=None):
    print(f"Status: {status}")
    if result:
        print("Result Answer:")
        print(result.get("answer"))
        print("\nEvidence Items Count:", len(result.get("evidence", [])))
        if result.get("intent_parsed"):
            print("Parsed Intent:", result["intent_parsed"])

async def main():
    # Run the DAG build manually to see what it generates
    from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
    from pipeline_function.pipeline.query_understanding.dag_planner import build_dag
    intent = await extract_ner_and_intent("Find me all robbery cases in Belagavi that occurred in narrow gullies where the attacker threatened the victim with a knife.")
    dag = await build_dag(intent)
    print("DAG Generated:", dag)
    await run_langgraph_pipeline("job-123", "Find me all robbery cases in Belagavi that occurred in narrow gullies where the attacker threatened the victim with a knife.", mock_callback)

asyncio.run(main())
