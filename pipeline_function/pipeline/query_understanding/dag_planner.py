import json
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete

DAG_PLANNER_SYSTEM = """You are a query planner for a criminal intelligence system.
Given a structured intent object, generate an execution plan as a JSON array of steps.
Each step: step_id, type, operation, params, depends_on (list of step_ids).
    IMPORTANT: `type` MUST be exactly one of: "graph", "rag", or "sql". 
    Use "graph" for standard crime/evidence/network lookups. 
    Use "rag" when the intent is `similarity_search` or when searching for a specific modus operandi narrative.
    Steps with no unmet dependencies run in parallel.
    Output ONLY valid JSON array. No preamble."""

async def build_dag(intent_object: dict) -> list:
    prompt = f"Intent object:\n{json.dumps(intent_object)}"
    try:
        raw = await llm_complete(prompt=prompt, system=DAG_PLANNER_SYSTEM,
                                  temperature=0.0, max_tokens=800)
    except Exception as e:
        print(f"[DAG Error] LLM call failed: {e}")
        return _default_plan(intent_object)
    try:
        clean_raw = raw.strip()
        if clean_raw.startswith("```json"):
            clean_raw = clean_raw[7:]
        if clean_raw.startswith("```"):
            clean_raw = clean_raw[3:]
        if clean_raw.endswith("```"):
            clean_raw = clean_raw[:-3]
        return json.loads(clean_raw.strip())
    except json.JSONDecodeError:
        return _default_plan(intent_object)

def _default_plan(intent: dict) -> list:
    return [
        {"step_id": 1, "type": "graph", "operation": "mo_search", "params": {}, "depends_on": []},
        {"step_id": 2, "type": "evidence_assembly", "operation": "merge_and_rank", "params": {}, "depends_on": [1]},
        {"step_id": 3, "type": "synthesis", "operation": "generate_response", "params": {}, "depends_on": [2]}
    ]
