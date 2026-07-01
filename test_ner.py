import asyncio
from unittest.mock import patch, AsyncMock
from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
import httpx

async def run_tests():
    print("\n--- Running NER + Resilience Tests ---")
    
    # 1. Test successful LLM parsing
    good_json = '{"entities": {"persons": ["Ravi"]}, "intent": "lookup", "urgency": "analytical", "sub_intents": []}'
    with patch("pipeline_function.pipeline.catalyst_resilient_client._raw_llm_complete", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = good_json
        res = await extract_ner_and_intent("Find Ravi")
        assert res["entities"]["persons"][0] == "Ravi", "Failed to extract entity"
        print("✅ Successful NER extraction working")
        
    # 2. Test cache hit
    # The previous test should have cached it!
    with patch("pipeline_function.pipeline.catalyst_resilient_client._raw_llm_complete", new_callable=AsyncMock) as mock_llm:
        res = await extract_ner_and_intent("Find Ravi")
        mock_llm.assert_not_called() # Should use cache
        assert res["entities"]["persons"][0] == "Ravi", "Cache didn't return valid entity"
        print("✅ LLM Caching (Layer 1) working")
        
    # 3. Test Markdown wrapped JSON extraction
    wrapped_json = 'Here is the result:\n```json\n{"entities": {"persons": ["Kumar"]}, "intent": "lookup", "urgency": "analytical", "sub_intents": []}\n```'
    with patch("pipeline_function.pipeline.catalyst_resilient_client._raw_llm_complete", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = wrapped_json
        res = await extract_ner_and_intent("Find Kumar")
        assert res["entities"]["persons"][0] == "Kumar", "Failed to extract JSON from Markdown"
        print("✅ Robust JSON decode working")
        
    # 4. Test Exponential Backoff on 429
    call_count = {"count": 0}
    async def mock_fail_then_succeed(*args, **kwargs):
        call_count["count"] += 1
        if call_count["count"] < 3:
            # Raise a mock 429
            req = httpx.Request("POST", "http://mock")
            resp = httpx.Response(429, request=req)
            raise httpx.HTTPStatusError("Rate limited", request=req, response=resp)
        return '{"entities": {"persons": ["Arrested"]}, "intent": "lookup", "urgency": "analytical", "sub_intents": []}'
        
    with patch("pipeline_function.pipeline.catalyst_resilient_client._raw_llm_complete", mock_fail_then_succeed):
        res = await extract_ner_and_intent("Find Arrested")
        assert call_count["count"] == 3, "Did not retry exactly 3 times"
        assert res["entities"]["persons"][0] == "Arrested"
        print("✅ Retry with Exponential Backoff (Layer 2) working")
        
    # 5. Test Graceful Degradation on persistent failure
    call_count["count"] = 0
    async def mock_fail_always(*args, **kwargs):
        call_count["count"] += 1
        req = httpx.Request("POST", "http://mock")
        resp = httpx.Response(429, request=req)
        raise httpx.HTTPStatusError("Rate limited", request=req, response=resp)
        
    with patch("pipeline_function.pipeline.catalyst_resilient_client._raw_llm_complete", mock_fail_always):
        res = await extract_ner_and_intent("Fail always")
        assert call_count["count"] == 3, "Did not exhaust retries"
        assert res.get("fallback") is True, "Did not return fallback structure"
        print("✅ Graceful Degradation (Layer 3) working")
        
    print("\nAll NER Pipeline tests passed successfully! 🚀\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
