import asyncio
from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
from pipeline_function.pipeline.query_understanding.entity_lookup_resolver import resolve_crime_sub_head, resolve_act_section
from pipeline_function.pipeline.query_understanding.dag_planner import build_dag
from pipeline_function.pipeline.evidence import EvidenceObject
from pipeline_function.pipeline.retrieval.executor import execute_retrieval
from pipeline_function.pipeline.confidence_engine import run_confidence_engine
from pipeline_function.pipeline.synthesis.synthesizer import synthesize

class PipelineState:
    def __init__(self, query: str, session_id: str):
        self.query = query
        self.session_id = session_id
        self.intent_object = {}
        self.dag = []
        self.evidence = None
        self.final_response = {}

_state_store = {}

async def run_pipeline_stages(input_state: dict, config: dict):
    query = input_state["query"]
    session_id = config["configurable"]["thread_id"]
    
    state = PipelineState(query, session_id)
    _state_store[session_id] = state
    try:
        # 1. NER and Intent
        yield "understanding_query", {"status": "Extracting entities..."}
        intent_obj = await extract_ner_and_intent(query)
        
        # Resolve Entities
        yield "resolving_entities", {"status": "Resolving entities..."}
        crime_types = intent_obj.get("entities", {}).get("crime_types", [])
        ipc_sections = intent_obj.get("entities", {}).get("ipc_sections", [])
        
        async def _gather_or_empty(coros):
            return await asyncio.gather(*coros) if coros else []

        resolved_crimes_raw, resolved_sections_raw = await asyncio.gather(
            _gather_or_empty([resolve_crime_sub_head(ct) for ct in crime_types]),
            _gather_or_empty([resolve_act_section(sec) for sec in ipc_sections])
        )
        resolved_crimes = [r for r in resolved_crimes_raw if r]
        resolved_sections = [r for r in resolved_sections_raw if r]
                 
        intent_obj["entities"]["resolved_crime_sub_heads"] = resolved_crimes
        intent_obj["entities"]["resolved_act_sections"] = resolved_sections
        
        state.intent_object = intent_obj
        
        # 2. DAG Planner
        yield "planning_execution", {"status": "Planning execution..."}
        dag = await build_dag(intent_obj)
        state.dag = dag
        
        # 3. Retrieval Execution
        yield "retrieving_evidence", {"status": "Retrieving evidence..."}
        urgency = intent_obj.get("urgency", "analytical")
        intent = intent_obj.get("intent", "lookup")
        evidence = EvidenceObject(
            query=query, session_id=session_id, urgency=urgency,
            intent=intent, entities=intent_obj.get("entities", {})
        )
        
        evidence = await execute_retrieval(dag, evidence, {"intent_object": intent_obj})
        
        # 4. Confidence Engine
        yield "scoring_evidence", {"status": "Scoring evidence..."}
        evidence = run_confidence_engine(evidence)
        state.evidence = evidence
        
        # 5. Synthesis
        yield "synthesizing_response", {"status": "Synthesizing response..."}
        final_response = await synthesize(evidence)
        
        final_result = {
            "answer": final_response["text"],
            "evidence": [
                {
                    "source": ",".join(e.sources), 
                    "data": {"fir_id": e.fir_id, "confidence": e.confidence, "score": e.relevance_score, "reasons": e.confidence_reasons}
                } for e in evidence.items
            ],
            "visualization": None,
            "intent_parsed": intent_obj,
            "reasoning_trace": final_response["reasoning_trace"]
        }
        
        state.final_response = final_result
        yield "done", final_result
    finally:
        _state_store.pop(session_id, None)

async def get_final_state(input_state: dict, config: dict):
    session_id = config["configurable"]["thread_id"]
    state = _state_store.get(session_id)
    if state:
        return state.final_response
    return {}
