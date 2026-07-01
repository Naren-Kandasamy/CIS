import asyncio
from unittest.mock import patch, AsyncMock
from pipeline_function.pipeline.template_router import run_template_router

async def run_tests():
    print("\n--- Running Template Router Tests ---")
    
    status_updates = []
    async def mock_write_status(job_id, session_id=None, query=None, status=None, result=None, error=None):
        status_updates.append((status, result, error))

    # Mock extract_ner_and_intent
    mock_intent = {
        "entities": {"crime_types": ["theft"], "ipc_sections": ["302"]},
        "intent": "lookup",
        "urgency": "analytical"
    }

    with patch("pipeline_function.pipeline.template_router.extract_ner_and_intent", new_callable=AsyncMock) as mock_ner, \
         patch("pipeline_function.pipeline.template_router.resolve_crime_sub_head", new_callable=AsyncMock) as mock_resolve_crime, \
         patch("pipeline_function.pipeline.template_router.resolve_act_section", new_callable=AsyncMock) as mock_resolve_act, \
         patch("pipeline_function.pipeline.template_router.kb_search", new_callable=AsyncMock) as mock_kb, \
         patch("pipeline_function.pipeline.template_router.llm_complete_resilient", new_callable=AsyncMock) as mock_llm:
         
         mock_ner.return_value = mock_intent
         mock_resolve_crime.return_value = "CSH123"
         mock_resolve_act.return_value = ("IPC", "302")
         mock_kb.return_value = {"results": ["Hit 1", "Hit 2"]}
         mock_llm.return_value = "This is the synthesized answer."
         
         await run_template_router("job-123", "Query here", mock_write_status)
         
         assert status_updates[0][0] == "understanding_query"
         assert status_updates[1][0] == "resolving_entities"
         assert status_updates[2][0] == "retrieving_evidence"
         assert status_updates[3][0] == "synthesizing_response"
         assert status_updates[4][0] == "done"
         
         final_result = status_updates[4][1]
         assert final_result["answer"] == "This is the synthesized answer."
         assert final_result["intent_parsed"]["entities"]["resolved_crime_sub_heads"] == ["CSH123"]
         
         print("✅ Template Router runs standard sequence and resolves entities correctly")

    print("\nAll Template Router tests passed successfully! 🚀\n")

if __name__ == "__main__":
    asyncio.run(run_tests())
