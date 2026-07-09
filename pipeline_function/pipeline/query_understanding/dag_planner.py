import json
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient as llm_complete

DAG_PLANNER_SYSTEM = """You are a query planner for a criminal intelligence system.
Given a structured intent object, generate an execution plan as a JSON array of steps.
Each step: step_id, type, operation, params, depends_on (list of step_ids).
    IMPORTANT: `type` MUST be exactly one of: "graph", "rag", or "sql". 
    Use "graph" for standard crime/evidence/network lookups. 
    Use "rag" for semantic KB similarity search — ALWAYS include a rag step alongside graph for any lookup or graph_search intent. RAG is the safety net for when graph data is sparse.
    For intent="lookup" or "graph_search": ALWAYS include BOTH a "graph" step AND a "rag" step running in parallel (depends_on: []).
    For intent="similarity_search": use rag only.
    Steps with no unmet dependencies run in parallel.
    Output ONLY valid JSON array. No preamble."""

async def build_dag(intent_object: dict) -> list:
    urgency = intent_object.get("urgency", "normal")
    system_prompt = DAG_PLANNER_SYSTEM
    if urgency == "field_urgent":
        system_prompt += "\n    URGENCY is field_urgent. Cap graph depth and DISABLE viz steps."

    prompt = f"Intent object:\n{json.dumps(intent_object)}"
    try:
        raw = await llm_complete(prompt=prompt, system=system_prompt,
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
    # BUG FIX: this used to also include "evidence_assembly" and "synthesis"
    # pseudo-steps -- neither is a real retrieval type executor.py recognizes
    # (only "graph"/"rag"/"sql"), so both silently fell through to
    # execute_retrieval's "unknown type" fallback and re-ran the SAME graph
    # query a second and third time on every DAG-planner failure. Assembly
    # and synthesis already happen as their own dedicated LangGraph nodes
    # (confidence_scoring, synthesizing_response) after retrieval -- they were
    # never meant to be retrieval steps here.
    return [
        {"step_id": 1, "type": "graph", "operation": "mo_search", "params": {}, "depends_on": []},
        {"step_id": 2, "type": "rag",   "operation": "kb_search",  "params": {"top_k": 10}, "depends_on": []},
    ]
