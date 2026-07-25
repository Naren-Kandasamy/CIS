import asyncio
from dotenv import load_dotenv

load_dotenv()

from pipeline_function.pipeline.retrieval.executor import execute_retrieval
from pipeline_function.pipeline.evidence import EvidenceObject

async def main():
    print("Testing Unified Retrieval (Graph + SQL + KB/RAG)...")
    
    # Mocking the state that the intent router (DAG planner) would produce
    state = {
        "intent": {
            "entities": {
                "locations": ["Belagavi"],
                "crime_types": ["robbery"]
            }
        }
    }
    
    # Mock DAG steps
    steps = [
        {"type": "graph"},
        {"type": "rag"},
        {"type": "sql"}
    ]
    
    # Create the evidence object
    evidence = EvidenceObject(
        query="Show me robberies in Belagavi",
        session_id="test_session",
        urgency="LOW",
        intent="data_retrieval",
        entities=state["intent"]["entities"]
    )
    
    # Run the unified retrieval (which gathers concurrently with timeouts)
    result_evidence = await execute_retrieval(steps, evidence, state)
    
    print("\n--- Unified Retrieval Complete ---")
    print(f"Total Combined Evidence Items: {len(result_evidence.items)}")
    
    for i, item in enumerate(result_evidence.items[:5]): # Show top 5
        print(f"\n[{i+1}] Score: {item.relevance_score} | Source: {item.evidence_path}")
        print(f"    Preview: {str(item.metadata)[:150]}...")
        
    print("\nReasoning Trace / Caveats:")
    print("Trace:", result_evidence.reasoning_trace)
    print("Caveats:", result_evidence.confidence_caveats)

if __name__ == "__main__":
    asyncio.run(main())
