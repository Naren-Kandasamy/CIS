import asyncio
import sys

from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline

CHAOS_QUERIES = [
    # Minimal inputs
    "Ravi",
    "him",
    "avan",
    "same case",
    # Unexpected/specific IPC sections
    "Show me all 302 IPC cases in Hubballi 2023",
    # Typos and misspellings
    "Suresh Babu assosiates",
    "Shivajinagara theft",
    # No matching data likely
    "Find me a murder case involving a lightsaber in Antarctica",
    # Pure Kannada / out of domain
    "ನಮಸ್ಕಾರ", # Namaskara (Hello)
    "ಕೊಲೆ ಪ್ರಕರಣಗಳ ಬಗ್ಗೆ ಹೇಳಿ", # Tell me about murder cases
    # Empty intents or conversational
    "hello",
    "what can you do?",
    ""
]

async def test_chaos():
    print(f"Running Chaos Test Suite: {len(CHAOS_QUERIES)} queries.")
    
    passed = 0
    failed = 0
    
    for i, query in enumerate(CHAOS_QUERIES, 1):
        print(f"\n[{i}/{len(CHAOS_QUERIES)}] Testing: '{query}'")
        
        captured_result = {}
        async def mock_callback(job_id, status, result=None, error=None):
            if status == "done" and result:
                captured_result.update(result)
            elif status == "failed":
                captured_result["error"] = error or "Unknown pipeline failure"
                
        try:
            # We enforce a strict timeout at the script level to catch infinite loops/hangs
            await asyncio.wait_for(
                run_langgraph_pipeline(f"job-chaos-{i}", query, mock_callback, []),
                timeout=25.0
            )
            
            if "error" in captured_result:
                print(f"❌ FAILED (Pipeline error): {captured_result['error']}")
                failed += 1
            elif not captured_result.get("answer"):
                print("❌ FAILED: Pipeline completed but returned no text answer.")
                failed += 1
            else:
                answer = captured_result["answer"].strip().replace('\\n', ' ')
                print(f"✅ PASSED (Response: {answer[:80]}...)")
                passed += 1
                
        except asyncio.TimeoutError:
            print("❌ FAILED: Pipeline hung and timed out after 25s.")
            failed += 1
        except Exception as e:
            print(f"❌ FAILED (Exception thrown): {str(e)}")
            failed += 1
            
    print(f"\n--- CHAOS TEST SUMMARY ---")
    print(f"Total: {len(CHAOS_QUERIES)} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)
        
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(test_chaos())
