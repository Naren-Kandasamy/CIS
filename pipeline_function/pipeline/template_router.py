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
    
    from pipeline_function.pipeline.query_understanding.dag_planner import build_dag
    from pipeline_function.pipeline.retrieval.executor import execute_retrieval
    from pipeline_function.pipeline.evidence import EvidenceObject
    
    dag_plan = await build_dag(intent_obj)
    intent = intent_obj.get("intent", "lookup")
    evidence_obj = EvidenceObject(
        query=query, 
        session_id=job_id, 
        urgency=intent_obj.get("urgency", "low"),
        intent=intent, 
        entities=intent_obj.get("entities", {})
    )
    
    evidence_obj = await execute_retrieval(dag_plan, evidence_obj, state={"intent": intent_obj})
    
    # Format the collected items for the LLM prompt
    evidence = []
    fir_ids = []
    for item in evidence_obj.items:
        evidence.append({
            "source": ",".join(item.sources),
            "fir_id": item.fir_id,
            "data": item.metadata
        })
        if item.fir_id:
            fir_ids.append(item.fir_id)
            
    # 4. Generate Visualization (Cytoscape Network)
    cytoscape_elements = []
    donut_data = []
    trend_data = []
    map_markers = []
    
    if fir_ids:
        from shared.graph_client import run_query
        
        # Add FIR nodes
        for item in evidence_obj.items:
            cytoscape_elements.append({
                "data": { "id": f"fir_{item.fir_id}", "label": f"{item.metadata.get('crime_type', 'FIR')}" },
                "classes": "fir"
            })
            
        # Query for associated persons
        person_query = """
        MATCH (p:Person)-[r]->(f:FIR)
        WHERE f.id IN $fir_ids
        RETURN p.id as person_id, type(r) as rel_type, f.id as fir_id
        """
        try:
            person_results = await run_query(person_query, {"fir_ids": fir_ids})
            added_persons = set()
            for row in person_results:
                pid = row["person_id"]
                rel = row["rel_type"]
                fid = row["fir_id"]
                
                # Add Person node if not exists
                if pid not in added_persons:
                    label = "Accused" if rel == "ACCUSED_IN" else "Victim"
                    cytoscape_elements.append({
                        "data": { "id": f"person_{pid}", "label": f"{label} {pid[:4]}" },
                        "classes": "person"
                    })
                    added_persons.add(pid)
                    
                # Add edge
                cytoscape_elements.append({
                    "data": { 
                        "id": f"edge_{pid}_{fid}", 
                        "source": f"person_{pid}", 
                        "target": f"fir_{fid}", 
                        "label": rel 
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
        # Dictionary of districts to base lat/lng
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
            
            # Default to Bengaluru if district not found
            base_lat, base_lng = district_coords.get(district, (12.9716, 77.5946))
            
            # Add small random jitter so they don't exactly overlap
            jitter_lat = (i % 3) * 0.005
            jitter_lng = (i % 4) * 0.005
            
            map_markers.append({
                "position": [base_lat + jitter_lat, base_lng + jitter_lng],
                "popup": f"FIR {item.fir_id[:8]} - {item.metadata.get('crime_type')}"
            })
            
        # Trend Data (Month aggregation based on FIR IDs or dates)
        # Mocking this slightly since the FIR dates are inside metadata
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
        
    # 5. Synthesis
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
        "visualization": visualization,
        "intent_parsed": intent_obj
    }
    
    await write_status_callback(job_id, status="done", result=final_result)
