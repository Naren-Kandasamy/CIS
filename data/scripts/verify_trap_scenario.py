import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline

async def verify_trap_scenario():
    print("Verifying trap scenario...")
    
    query = "Find cases where the suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face."
    
    # We will use a mock callback to capture the result
    captured_result = {}
    async def mock_callback(job_id, status, result=None, error=None):
        if status == "done" and result:
            captured_result.update(result)
            
    await run_langgraph_pipeline("job-trap-verify", query, mock_callback, [])
    
    if not captured_result:
        print("❌ FAILED: Pipeline returned no result.")
        sys.exit(1)
        
    print("Captured Result (DAG, Intents, etc.):")
    print(captured_result.get("reasoning_trace"))
    print("Evidence generated:", len(captured_result.get("evidence", [])))
    
    evidence_items = captured_result.get("evidence", [])
    
    trap_firs = [e for e in evidence_items if e.get("fir_id") in ["TRAP-FIR-001", "TRAP-FIR-002"]]
    
    if not trap_firs:
        print("❌ FAILED: Trap FIRs were not retrieved by the pipeline.")
        sys.exit(1)
        
    for item in trap_firs:
        conf = item.get("confidence")
        fir_id = item.get("fir_id")
        
        if conf in ["high", "medium"]:
            print(f"❌ FAILED: Trap FIR {fir_id} was assigned HIGH/MEDIUM confidence ({conf}). The confidence engine is broken!")
            sys.exit(1)
            
        print(f"✅ Trap FIR {fir_id} correctly assigned {conf} confidence.")
        
    print("✅ TRAP SCENARIO PASSED! Launch blocker cleared.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(verify_trap_scenario())
