import asyncio
from pipeline_function.pipeline.evidence import EvidenceObject

TIMEOUT_BUDGETS = {"graph": 5.0, "rag": 3.0, "sql": 4.0}

async def execute_with_timeout(coro, source_type: str, evidence: EvidenceObject):
    timeout = TIMEOUT_BUDGETS.get(source_type, 5.0)
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        evidence.reasoning_trace.append(
            f"WARNING: {source_type} retrieval exceeded {timeout}s budget -- "
            f"proceeding without this source"
        )
        evidence.confidence_caveats.append(f"{source_type}_unavailable")
        return None
    except Exception as e:
        evidence.reasoning_trace.append(f"WARNING: {source_type} retrieval failed: {str(e)}")
        evidence.confidence_caveats.append(f"{source_type}_unavailable")
        return None

from shared.graph_client import run_query

async def run_graph_step(step, state):
    intent = state.get("intent", {})
    entities = intent.get("entities", {})
    
    city = entities.get("city", "")
    locations = entities.get("locations", [])
    if isinstance(locations, str): locations = [locations]
    
    crime_types = entities.get("crime_types", [])
    weapon = entities.get("weapon", "")
    
    # Base Cypher query
    cypher = "MATCH (f:FIR) WHERE 1=1"
    params = {}
    
    if city:
        cypher += " AND toLower(f.district) CONTAINS toLower($city)"
        params["city"] = city
        
    if locations:
        # Split locations into words for more robust matching (e.g. "narrow gullies" matches "narrow gully")
        words = []
        for loc in locations:
            words.extend([w for w in loc.split() if len(w) > 3])  # skip small words like 'in', 'at'
        if not words:
            words = locations
            
        loc_clause = " OR ".join([f"(toLower(f.modus_operandi) CONTAINS toLower($loc_{i}) OR toLower(f.narrative) CONTAINS toLower($loc_{i}))" for i in range(len(words))])
        if loc_clause:
            cypher += f" AND ({loc_clause})"
            for i, word in enumerate(words):
                params[f"loc_{i}"] = word
                
        
    if crime_types:
        # Match any of the extracted crime types
        types_clause = " OR ".join([f"toLower(f.crime_type) CONTAINS toLower($ctype_{i})" for i in range(len(crime_types))])
        if types_clause:
            cypher += f" AND ({types_clause})"
            for i, ct in enumerate(crime_types):
                params[f"ctype_{i}"] = ct
                
    if weapon:
        cypher += " AND (toLower(f.modus_operandi) CONTAINS toLower($weapon) OR toLower(f.narrative) CONTAINS toLower($weapon))"
        params["weapon"] = weapon
        
    # Return top relevant FIRs
    cypher += " RETURN f.id as fir_id, f.crime_no as crime_no, f.district as district, f.crime_type as crime_type, f.modus_operandi as modus_operandi, f.narrative as narrative, f.date as date LIMIT 10"
    
    print(f"Executing Cypher: {cypher} with params {params}")
    try:
        results = await run_query(cypher, params)
        print(f"Got {len(results)} results from graph")
    except Exception as e:
        print(f"Graph query failed: {e}")
        results = []
    
    # Format for the EvidenceObject
    formatted = []
    for row in results:
        formatted.append({
            "fir_id": row["fir_id"],
            "score": 0.9,
            "path": f"FIR({row['crime_no']}) in {row['district']}",
            "metadata": {
                "crime_type": row["crime_type"],
                "modus_operandi": row["modus_operandi"],
                "narrative": row["narrative"],
                "Date": row.get("date", ""),
                "district": row.get("district", "")
            }
        })
    return formatted

from shared.catalyst_client import kb_search

async def run_rag_step(step, query):
    """Execute a KB semantic search step."""
    top_k = step.get("params", {}).get("top_k", 10)
    result = await kb_search(query, top_k=top_k)
    return result

async def run_sql_step(step, entities):
    """Execute a structured SQL retrieval step."""
    # Since search_cases_by_district doesn't exist yet, we mock or implement a simple ZTSQL query
    from shared.catalyst_client import ztsql_query
    locations = entities.get("locations", [])
    city = entities.get("city", "")
    
    district = ""
    if locations: district = locations[0]
    elif city: district = city
    
    if not district:
        return []
        
    query = "SELECT * FROM cases WHERE district_name LIKE ? LIMIT 10"
    try:
        res = await ztsql_query(query, [f"%{district}%"])
        return res
    except Exception as e:
        print(f"SQL failed: {e}")
        return []

async def execute_retrieval(steps: list, evidence: EvidenceObject, state: dict):
    tasks = []
    for step in steps:
        step_type = step.get("type", "graph")
        if step_type in ("data_retrieval", "retrieval"): step_type = "graph"
        
        if step_type == "graph":
            coro = run_graph_step(step, state)
        elif step_type == "rag":
            coro = run_rag_step(step, evidence.query)
        elif step_type == "sql":
            coro = run_sql_step(step, evidence.entities)
        else:
            coro = run_graph_step(step, state)  # Default fallback
            
        tasks.append(execute_with_timeout(coro, step_type, evidence))
        step["_normalized_type"] = step_type

    results = await asyncio.gather(*tasks)

    for step, result in zip(steps, results):
        if result is None:
            continue
        step_type = step.get("_normalized_type", "graph")
        
        if step_type == "rag":
            evidence.add_rag_results(result)
        elif step_type == "graph":
            evidence.add_graph_results(result)
        elif step_type == "sql":
            evidence.add_sql_results(result)

    evidence.rank()
    return evidence
