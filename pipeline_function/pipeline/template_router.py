import json
from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
from pipeline_function.pipeline.query_understanding.entity_lookup_resolver import resolve_crime_sub_head, resolve_act_section
from shared.catalyst_client import ztsql_query, kb_search
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient

async def run_template_router(job_id: str, query: str, write_status_callback):
    """
    Phase 2 Template Router.
    Executes a rigid sequence: NER -> Resolve -> Branch based on intent -> Synthesize.
    Replaces the empty skeleton and unblocks the SSE UI stream.
    """
    # 1. Extract NER & Intent
    await write_status_callback(job_id, status="understanding_query")
    intent_obj = await extract_ner_and_intent(query)
    
    # 2. Resolve Entities
    await write_status_callback(job_id, status="resolving_entities")
    crime_types = intent_obj["entities"].get("crime_types", [])
    resolved_crimes = []
    for ct in crime_types:
        resolved = await resolve_crime_sub_head(ct)
        if resolved:
             resolved_crimes.append(resolved)
             
    ipc_sections = intent_obj["entities"].get("ipc_sections", [])
    resolved_sections = []
    for sec in ipc_sections:
        resolved = await resolve_act_section(sec)
        if resolved:
             resolved_sections.append(resolved)
             
    intent_obj["entities"]["resolved_crime_sub_heads"] = resolved_crimes
    intent_obj["entities"]["resolved_act_sections"] = resolved_sections
    
    # 3. Route Based on Intent
    await write_status_callback(job_id, status="retrieving_evidence")
    
    intent = intent_obj.get("intent", "lookup")
    evidence = []
    
    try:
        if intent == "lookup" or intent == "broad_search":
            # RAG fallback lookup
            res = await kb_search(query, top_k=5)
            # Make sure we don't crash if mock kb_search returns empty/different structure
            hits = res.get("results", []) if isinstance(res, dict) else []
            evidence = [{"source": "kb", "data": hit} for hit in hits]
        elif intent == "graph_search":
            evidence = [{"source": "mock_graph", "data": f"Graph data found for {intent_obj['entities'].get('persons', ['Unknown'])[0]}"}]
        elif intent == "statistics":
            evidence = [{"source": "ztsql", "data": "Statistics aggregated"}]
        else:
            evidence = [{"source": "mock", "data": "General evidence"}]
    except Exception as e:
        evidence = [{"source": "error", "data": f"Retrieval failed: {str(e)}"}]
        
    # 4. Synthesis
    await write_status_callback(job_id, status="synthesizing_response")
    
    system = "You are an AI assistant for the PS-1 police system. Answer based ONLY on the evidence provided."
    prompt = f"Query: {query}\nEvidence: {json.dumps(evidence)}"
    
    try:
        answer = await llm_complete_resilient(prompt=prompt, system=system, temperature=0.1, max_tokens=800)
    except Exception:
        # LOCAL DEV fallback: LLM unavailable (no API key). Return structured mock
        # so the SSE stream always completes with 'done' rather than stalling.
        parsed_intent = intent_obj.get("intent", "lookup")
        persons = intent_obj["entities"].get("persons", [])
        locs    = intent_obj["entities"].get("locations", [])
        crimes  = intent_obj["entities"].get("crime_types", [])
        answer = (
            f"[Mock Response — LLM unavailable locally]\n\n"
            f"Query understood: intent='{parsed_intent}'"
            + (f", persons={persons}" if persons else "")
            + (f", locations={locs}" if locs else "")
            + (f", crime_types={crimes}" if crimes else "")
            + f".\n\nEvidence retrieved: {len(evidence)} item(s). "
            "Connect to Catalyst Qwen API for a real synthesized response."
        )
        
    final_result = {
        "answer": answer,
        "evidence": evidence,
        "visualization": None,
        "intent_parsed": intent_obj
    }
    
    await write_status_callback(job_id, status="done", result=final_result)
