import operator
from typing import Annotated, Sequence, TypedDict
from langgraph.graph import StateGraph, END
import json

from pipeline_function.pipeline.query_understanding.ner_intent import extract_ner_and_intent
from pipeline_function.pipeline.query_understanding.entity_lookup_resolver import resolve_crime_sub_head, resolve_act_section
from pipeline_function.pipeline.query_understanding.dag_planner import build_dag
from pipeline_function.pipeline.retrieval.executor import execute_retrieval
from pipeline_function.pipeline.evidence import EvidenceObject
from pipeline_function.pipeline.catalyst_resilient_client import llm_complete_resilient
from pipeline_function.pipeline.confidence_engine import run_confidence_engine

# State schema for the graph
class AgentState(TypedDict):
    job_id: str
    query: str
    write_status_callback: any
    intent_obj: dict
    dag: list
    evidence: EvidenceObject
    visualization: dict
    final_response: str
    history: list

async def understanding_query_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="understanding_query")
    intent_obj = await extract_ner_and_intent(state["query"])
    return {"intent_obj": intent_obj}

async def resolving_entities_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="resolving_entities")
    intent_obj = state["intent_obj"]
    
    crime_types = intent_obj["entities"].get("crime_types", [])
    ipc_sections = intent_obj["entities"].get("ipc_sections", [])
    
    import asyncio
    crime_results, section_results = await asyncio.gather(
        asyncio.gather(*[resolve_crime_sub_head(ct) for ct in crime_types]),
        asyncio.gather(*[resolve_act_section(sec) for sec in ipc_sections])
    )
    
    resolved_crimes = [r for r in crime_results if r]
    resolved_sections = [r for r in section_results if r]
             
    intent_obj["entities"]["resolved_crime_sub_heads"] = resolved_crimes
    intent_obj["entities"]["resolved_act_sections"] = resolved_sections
    return {"intent_obj": intent_obj}

async def planning_execution_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="planning_execution")
    dag = await build_dag(state["intent_obj"])
    return {"dag": dag}

async def retrieving_evidence_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="retrieving_evidence")
    
    intent_obj = state["intent_obj"]
    urgency = intent_obj.get("urgency", "analytical")
    intent = intent_obj.get("intent", "lookup")
    evidence_obj = EvidenceObject(
        query=state["query"],
        session_id=state["job_id"],
        urgency=urgency,
        intent=intent,
        entities=intent_obj.get("entities", {})
    )
    
    evidence_obj = await execute_retrieval(state["dag"], evidence_obj, {"intent_object": intent_obj})
    return {"evidence": evidence_obj}

async def confidence_scoring_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="confidence_scoring")
    evidence_obj = state["evidence"]
    evidence_obj = run_confidence_engine(evidence_obj)
    return {"evidence": evidence_obj}

async def building_visualization_node(state: AgentState):
    evidence_obj = state["evidence"]
    fir_ids = []
    for item in evidence_obj.items:
        if item.fir_id:
            fir_ids.append(item.fir_id)
            
    cytoscape_elements = []
    donut_data = []
    trend_data = []
    map_markers = []
    
    if fir_ids:
        from shared.graph_client import run_query
        # Create FIR nodes
        for item in evidence_obj.items:
            if not item.fir_id: continue
            cytoscape_elements.append({
                "data": {
                    "id": item.fir_id,
                    "label": "FIR\n" + item.fir_id[:8],
                    "type": "fir",
                    "details": item.metadata.get("crime_type", "Unknown")
                },
                "classes": "fir"
            })
            
        person_query = """
        MATCH (p:Person)-[r]->(f:FIR)
        WHERE f.id IN $fir_ids
        RETURN p.id as person_id, type(r) as rel_type, f.id as fir_id
        """
        try:
            results = await run_query(person_query, {"fir_ids": fir_ids})
            persons_added = set()
            for r in results:
                p_id = r["person_id"]
                if p_id not in persons_added:
                    cytoscape_elements.append({
                        "data": {
                            "id": p_id,
                            "label": p_id[:8],
                            "type": "person",
                            "details": "Person"
                        },
                        "classes": "person"
                    })
                    persons_added.add(p_id)
                cytoscape_elements.append({
                    "data": {
                        "id": f"{p_id}_{r['fir_id']}",
                        "source": p_id,
                        "target": r["fir_id"],
                        "label": r["rel_type"]
                    }
                })
        except Exception as e:
            print(f"Failed to build visualization graph: {e}")
            
        # Recharts Donut Data (Crime Type Distribution)
        crime_counts = {}
        for item in evidence_obj.items:
            ctype = item.metadata.get('crime_type', 'Unknown')
            if not ctype: ctype = 'Unknown'
            crime_counts[ctype] = crime_counts.get(ctype, 0) + 1
            
        donut_data = [{"name": k, "value": v} for k, v in crime_counts.items()]
        
        # Leaflet Map Data (Markers)
        district_coords = {
            "BELAGAVI": (15.8497, 74.4977),
            "BENGALURU CITY": (12.9716, 77.5946),
            "MYSURU CITY": (12.2958, 76.6394),
            "MANGALURU CITY": (12.8715, 74.8524),
            "HUBBALLI DHARWAD CITY": (15.3647, 75.1240)
        }
        map_markers = []
        for i, item in enumerate(evidence_obj.items[:10]):
            district = item.metadata.get('district', '').upper()
            base_lat, base_lng = district_coords.get(district, (12.9716, 77.5946))
            jitter_lat = (i % 3) * 0.005
            jitter_lng = (i % 4) * 0.005
            map_markers.append({
                "position": [base_lat + jitter_lat, base_lng + jitter_lng],
                "popup": f"FIR {item.fir_id[:8]} - {item.metadata.get('crime_type')}"
            })
            
        # Trend Data (Month aggregation based on FIR IDs or dates)
        trend_counts = {}
        for item in evidence_obj.items:
            date_str = item.metadata.get('Date', '')
            if date_str and len(date_str) >= 7:
                month = date_str[:7] # YYYY-MM
                trend_counts[month] = trend_counts.get(month, 0) + 1
        
        trend_data = [{"name": k, "crimes": v} for k, v in sorted(trend_counts.items())]

    visualization = {
        "cytoscape": { "elements": cytoscape_elements },
        "recharts": { "donut": donut_data, "trend": trend_data },
        "leaflet": { "markers": map_markers }
    }
    return {"visualization": visualization}

async def synthesizing_response_node(state: AgentState):
    await state["write_status_callback"](state["job_id"], status="synthesizing_response")
    
    evidence_obj = state["evidence"]
    query = state["query"]
    
    evidence_dicts = []
    for item in evidence_obj.items[:10]:
        evidence_dicts.append({
            "source": ",".join(item.sources),
            "fir_id": item.fir_id,
            "confidence": item.confidence,
            "relevance_score": item.relevance_score,
            "data": item.metadata
        })
        
    system = "You are an AI assistant for the PS-1 police system. Answer based ONLY on the evidence provided."
    if state.get("history"):
        history_str = "\n".join([f"Q: {h['q']}\nA: {h['a']}" for h in state["history"][-3:]])
        prompt = f"Previous conversation history:\n{history_str}\n\nCurrent Query: {query}\n\nEvidence: {json.dumps(evidence_dicts)}"
    else:
        prompt = f"Query: {query}\nEvidence: {json.dumps(evidence_dicts)}"
        
    try:
        ans = await llm_complete_resilient(prompt=prompt, system=system, temperature=0.2, max_tokens=1500)
    except Exception as e:
        print(f"[Synthesis Error] LLM call failed: {e}")
        ans = "The system successfully retrieved evidence for your query, but the generation model is currently unavailable or under heavy load. Please refer to the evidence panels for retrieved data."
    
    return {"final_response": ans}

# Define the graph compilation inside the runner for thread-safety
async def run_langgraph_pipeline(job_id: str, query: str, write_status_callback, history: list = None):
    workflow = StateGraph(AgentState)
    
    workflow.add_node("understanding_query", understanding_query_node)
    workflow.add_node("resolving_entities", resolving_entities_node)
    workflow.add_node("planning_execution", planning_execution_node)
    workflow.add_node("retrieving_evidence", retrieving_evidence_node)
    workflow.add_node("confidence_scoring", confidence_scoring_node)
    workflow.add_node("building_visualization", building_visualization_node)
    workflow.add_node("synthesizing_response", synthesizing_response_node)
    
    workflow.add_edge("understanding_query", "resolving_entities")
    workflow.add_edge("resolving_entities", "planning_execution")
    workflow.add_edge("planning_execution", "retrieving_evidence")
    workflow.add_edge("retrieving_evidence", "confidence_scoring")
    workflow.add_edge("confidence_scoring", "building_visualization")
    workflow.add_edge("building_visualization", "synthesizing_response")
    workflow.add_edge("synthesizing_response", END)
    
    workflow.set_entry_point("understanding_query")
    app = workflow.compile()

    initial_state = {
        "job_id": job_id,
        "query": query,
        "write_status_callback": write_status_callback,
        "history": history or []
    }
    
    final_state = await app.ainvoke(initial_state)
    
    # Save output
    evidence_dicts = []
    for item in final_state["evidence"].items:
        evidence_dicts.append({
            "source": ",".join(item.sources),
            "fir_id": item.fir_id,
            "confidence": item.confidence,
            "relevance_score": item.relevance_score,
            "data": item.metadata
        })
        
    result_data = {
        "answer": final_state["final_response"],
        "evidence": evidence_dicts,
        "visualization": final_state["visualization"],
        "intent_parsed": final_state["intent_obj"],
        "reasoning_trace": final_state["evidence"].reasoning_trace
    }
    
    await write_status_callback(job_id, status="done", result=result_data)
