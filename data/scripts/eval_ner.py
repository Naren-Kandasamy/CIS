import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent

EVAL_SUITE = [
    {
        "query": "Show me all robbery cases in Belagavi from last year",
        "expected_intent": "lookup",
        "expected_entities": {"locations": ["Belagavi"], "crime_types": ["robbery"]}
    },
    {
        "query": "Who are the associates of Suresh?",
        "expected_intent": "graph_search",
        "expected_entities": {"persons": ["Suresh"]}
    },
    {
        "query": "Are there any 302 IPC cases in Hubballi?",
        "expected_intent": "lookup",
        "expected_entities": {"locations": ["Hubballi"], "ipc_sections": ["302"]}
    },
    {
        "query": "Summarize the FIR 199991234202100001",
        "expected_intent": "summarize",
        "expected_entities": {"fir_ids": ["199991234202100001"]}
    },
    {
        "query": "Find cases where the suspect broke in through the rear window using a specialized glass cutter",
        "expected_intent": "lookup",
        "expected_entities": {}
    },
    {
        "query": "Has Ravi committed any crimes in Mysuru?",
        "expected_intent": "lookup",
        "expected_entities": {"persons": ["Ravi"], "locations": ["Mysuru"]}
    },
    {
        "query": "Is there any link between Suresh and Ramesh?",
        "expected_intent": "graph_search",
        "expected_entities": {"persons": ["Suresh", "Ramesh"]}
    },
    {
        "query": "Tell me about the theft at Shivaji Nagar",
        "expected_intent": "lookup",
        "expected_entities": {"locations": ["Shivaji Nagar"], "crime_types": ["theft"]}
    },
    {
        "query": "List all cyber crime cases involving phishing",
        "expected_intent": "lookup",
        "expected_entities": {"crime_types": ["cyber crime", "phishing"]}
    },
    {
        "query": "Give me a detailed statistical report on murders in Karnataka",
        "expected_intent": "statistics",
        "expected_entities": {"locations": ["Karnataka"], "crime_types": ["murders"]}
    }
]

async def eval_single(test_case):
    query = test_case["query"] + " now"
    try:
        # Evaluate
        result = await extract_ner_and_intent(query)
        print(f"\\n[DEBUG RAW PAYLOAD]: {result}\\n")
        
        # Check intent
        if result.get("fallback") and test_case["expected_intent"] != "lookup":
            return False, f"Fallback triggered"
            
        if result.get("intent") != test_case["expected_intent"]:
            # Sometimes statistical analysis is mapped to lookup + aggregation, which is fine, 
            # but let's strictly check for our test cases.
            if result.get("intent") == "lookup" and test_case["expected_intent"] == "statistical_analysis":
                 pass # Forgiving rule
            else:
                return False, f"Intent mismatch: Expected {test_case['expected_intent']}, got {result.get('intent')}"
            
        # Check entities
        extracted = result.get("entities", {})
        for key, expected_values in test_case["expected_entities"].items():
            extracted_list = [str(x).lower() for x in extracted.get(key, [])]
            if key == "locations" and extracted.get("city"):
                extracted_list.append(str(extracted.get("city")).lower())
            for exp in expected_values:
                # We check if the expected value is at least a substring (e.g. "robbery" in "robbery cases")
                if not any(exp.lower() in ex for ex in extracted_list):
                     return False, f"Entity missing: Expected '{exp}' in {key}, got {extracted.get(key, [])}"
                     
        return True, "Success"
    except Exception as e:
         return False, f"Exception: {str(e)}"

async def run_eval_suite():
    print(f"Running NER Eval Suite on {len(EVAL_SUITE)} queries...")
    
    passed = 0
    
    # Run sequentially to avoid aggressive rate limits on Groq
    for i, test in enumerate(EVAL_SUITE, 1):
        print(f"[{i}/{len(EVAL_SUITE)}] Query: '{test['query']}'")
        is_pass, reason = await eval_single(test)
        if is_pass:
            print("  ✅ PASS")
            passed += 1
        else:
            print(f"  ❌ FAIL: {reason}")
            
        # Small delay to prevent 429 Too Many Requests
        await asyncio.sleep(2.0)
            
    pass_rate = (passed / len(EVAL_SUITE)) * 100
    print(f"\\n--- EVALUATION COMPLETE ---")
    print(f"Pass Rate: {pass_rate:.1f}% ({passed}/{len(EVAL_SUITE)})")
    
    if pass_rate >= 90.0:
        print("✅ Gate passed: Pass rate >= 90%")
        sys.exit(0)
    else:
        print("❌ Gate failed: Pass rate below 90%")
        sys.exit(1)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run_eval_suite())
