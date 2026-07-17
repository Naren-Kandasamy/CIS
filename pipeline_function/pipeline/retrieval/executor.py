import asyncio
import logging
from pipeline_function.pipeline.evidence import EvidenceObject

logger = logging.getLogger(__name__)

TIMEOUT_BUDGETS = {"graph": 5.0, "rag": 3.0, "sql": 4.0}

# BUG FIX: hard caps on the number of location/crime_type terms (and each
# raw string's length) that run_graph_step will turn into Cypher OR-branches
# and bound params. Previously unbounded -- entities.locations/crime_types
# come straight from an LLM NER call capped only at max_tokens=500, which can
# still return on the order of 100-200 short strings (or one long run-on
# string), producing a WHERE clause with hundreds of OR branches/params per
# request. Mirrors the resolved_crime_sub_heads[:3] cap already used in
# run_sql_step.
MAX_ENTITY_TERMS = 20
MAX_ENTITY_STRING_LEN = 100

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
    
    # Handle Algorithmic Queries
    if step.get("operation") == "pagerank":
        # Execute Degree Centrality / Mock PageRank based on FIR counts
        cypher = """
        MATCH (p:Person)-[:ACCUSED_IN]->(f:FIR)
        """
        params = {}
        if city:
            cypher += "WHERE toLower(f.district) CONTAINS toLower($city)\n"
            params["city"] = city
            
        cypher += """
        WITH p, count(f) as rank
        ORDER BY rank DESC LIMIT 5
        RETURN p.id as person_id, rank
        """
        
        # BUG FIX: was an unconditional print() of the full Cypher text and bound
        # params (district names etc.) to stdout on every call -- in the Catalyst
        # deployment that lands in platform-level log aggregation, which is
        # retained longer / more broadly readable than app-level CIS access.
        # logger.debug() is a no-op unless the root logger is explicitly set to
        # DEBUG, so nothing is logged in production by default.
        logger.debug("Executing Algorithmic Cypher: %s with params %s", cypher, params)
        results = await run_query(cypher, params)
        
        formatted = []
        for row in results:
            formatted.append({
                "fir_id": f"Person: {row['person_id']}",
                "score": 0.99,
                "path": f"Algorithm: PageRank/Centrality",
                "metadata": {
                    "Accused ID": row["person_id"],
                    "Page Rank Score": str(row["rank"]),
                    "district": city
                }
            })
        return formatted
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
        for loc in locations[:MAX_ENTITY_TERMS]:
            words.extend([w for w in loc[:MAX_ENTITY_STRING_LEN].split() if len(w) >= 3])  # skip only 1-2 char words like 'in', 'at'
        words = words[:MAX_ENTITY_TERMS]
        if not words:
            words = locations[:MAX_ENTITY_TERMS]

        loc_clause = " OR ".join([f"(toLower(f.modus_operandi) CONTAINS toLower($loc_{i}) OR toLower(f.narrative) CONTAINS toLower($loc_{i}))" for i in range(len(words))])
        if loc_clause:
            cypher += f" AND ({loc_clause})"
            for i, word in enumerate(words):
                params[f"loc_{i}"] = word
                
        
    if crime_types:
        # Match any of the extracted crime types against type, MO, and narrative using keywords
        # BUG FIX: same MAX_ENTITY_TERMS/MAX_ENTITY_STRING_LEN cap as the locations
        # block above -- crime_types comes from the same uncapped NER output.
        words = []
        for ct in crime_types[:MAX_ENTITY_TERMS]:
            words.extend([w for w in ct[:MAX_ENTITY_STRING_LEN].split() if len(w) >= 3])
        words = words[:MAX_ENTITY_TERMS]
        if not words:
            words = crime_types[:MAX_ENTITY_TERMS]

        types_clause = " OR ".join([f"(toLower(f.crime_type) CONTAINS toLower($ctype_{i}) OR toLower(f.modus_operandi) CONTAINS toLower($ctype_{i}) OR toLower(f.narrative) CONTAINS toLower($ctype_{i}))" for i in range(len(words))])
        if types_clause:
            cypher += f" AND ({types_clause})"
            for i, word in enumerate(words):
                params[f"ctype_{i}"] = word
                
    if weapon:
        cypher += " AND (toLower(f.modus_operandi) CONTAINS toLower($weapon) OR toLower(f.narrative) CONTAINS toLower($weapon))"
        params["weapon"] = weapon
        
    # Return top relevant FIRs, along with any Accused linked via ACCUSED_IN --
    # needed so exclusion demotion (confidence_engine.py) can tell which
    # accused persons an evidence item is about. OPTIONAL MATCH so FIRs with
    # no linked Accused still come back (empty accused_ids, not dropped).
    cypher += """
 WITH f
 OPTIONAL MATCH (a:Accused)-[:ACCUSED_IN]->(f)
 WITH f, collect(DISTINCT a.id) AS accused_ids
 RETURN f.id as fir_id, f.crime_no as crime_no, f.district as district, f.crime_type as crime_type, f.modus_operandi as modus_operandi, f.narrative as narrative, f.date as date, accused_ids
 LIMIT 10"""

    # BUG FIX: was an unconditional print() of the full Cypher text and bound
    # params -- suspect/location names, MO descriptions, weapon mentions pulled
    # from the officer's query -- to stdout on every graph retrieval call. See
    # the identical fix/rationale on the pagerank branch above.
    logger.debug("Executing Cypher: %s with params %s", cypher, params)
    # BUG FIX: this used to catch every exception and return [] here,
    # indistinguishable from "the query legitimately found nothing" --
    # execute_with_timeout (which wraps this coroutine) already has its own
    # except-Exception handler that correctly marks the source unavailable
    # in confidence_caveats/reasoning_trace, so let real failures propagate
    # to it instead of swallowing them here.
    results = await run_query(cypher, params)
    print(f"Got {len(results)} results from graph")

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
                "district": row.get("district", ""),
                "accused_ids": row.get("accused_ids") or []
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
    """
    Execute a structured SQL retrieval step, filtered by resolved crime
    sub-head classification.

    BUG FIX: previously filtered by district_name against the `cases` table,
    a column that was never actually populated by any real ingestion script
    (see sql_client.py) -- this always returned empty/erroring results,
    silently, for every query ever routed through SQL. Now delegates to
    sql_client.py's search_cases_by_crime_sub_head(), which filters on
    crime_sub_head_id -- a column the real seeding scripts do populate, and a
    value entity_lookup_resolver.py already resolves from free-text mentions
    of a crime type earlier in the pipeline.
    """
    from pipeline_function.pipeline.retrieval.sql_client import search_cases_by_crime_sub_head
    resolved_crime_sub_heads = entities.get("resolved_crime_sub_heads", [])
    if not resolved_crime_sub_heads:
        return []

    # BUG FIX: this used to catch every exception (network errors, a broken
    # query) and return [] here -- indistinguishable from "no matching cases,"
    # so execute_with_timeout never saw the failure and sql_unavailable never
    # reached confidence_caveats/reasoning_trace. Real failures now propagate
    # to execute_with_timeout's own except-Exception handler instead.
    results = []
    for csh_id in resolved_crime_sub_heads[:3]:
        results.extend(await search_cases_by_crime_sub_head(csh_id, limit=10))
    return results

async def execute_retrieval(steps: list, evidence: EvidenceObject, state: dict):
    # BUG FIX: an unrecognized step type (e.g. a non-retrieval pseudo-step
    # like "evidence_assembly"/"synthesis" that a DAG plan shouldn't have
    # included in the first place) used to silently fall back to
    # run_graph_step -- re-running the same graph query once per unrecognized
    # step. Unrecognized types are now skipped with a warning instead of
    # silently duplicating a real retrieval call.
    tasks = []
    normalized_steps = []
    for step in steps:
        step_type = step.get("type", "graph")
        if step_type in ("data_retrieval", "retrieval"):
            step_type = "graph"

        if step_type == "graph":
            coro = run_graph_step(step, state)
        elif step_type == "rag":
            coro = run_rag_step(step, evidence.query)
        elif step_type == "sql":
            coro = run_sql_step(step, evidence.entities)
        else:
            print(f"Skipping DAG step with unrecognized type {step_type!r}: {step}")
            continue

        tasks.append(execute_with_timeout(coro, step_type, evidence))
        normalized_steps.append((step, step_type))

    results = await asyncio.gather(*tasks)

    for (step, step_type), result in zip(normalized_steps, results):
        if result is None:
            continue

        if step_type == "rag":
            evidence.add_rag_results(result)
        elif step_type == "graph":
            evidence.add_graph_results(result)
        elif step_type == "sql":
            await evidence.add_sql_results(result)

    evidence.rank()
    return evidence
