# PS-1 Phase 5, Item 3: Proactive Cold-Case Matching
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 3.

import uuid
from datetime import datetime, timezone
from shared.exclusion_engine import get_active_exclusions
from shared.review_queue_models import ReviewQueueItem
from shared.review_queue_engine import push_review_item
from shared.catalyst_client import kb_search
from shared.graph_client import run_query, run_write

COLD_CASE_MATCH_THRESHOLD = 0.75
COLD_STATUS_VALUES = {"open", "cold"}

async def run_cold_case_match(new_fir, shared_mo_matches: list[dict]):
    """
    Filters and routes MO similarity matches to the review queue.
    Suppresses matches that are ruled out by active exclusions.
    """
    # Standardize fir properties to handle both dict and Pydantic object
    fir_id = new_fir.get("fir_internal_id") if isinstance(new_fir, dict) else getattr(new_fir, "id", None)
    crime_no = new_fir.get("crime_no") if isinstance(new_fir, dict) else getattr(new_fir, "crime_no", None)
    
    if not fir_id or not crime_no:
        print("[ColdCaseMatcher] Missing fir_internal_id or crime_no on new FIR.")
        return

    for match in shared_mo_matches:
        if match["matched_fir_status"] not in COLD_STATUS_VALUES:
            continue
        if match["score"] < COLD_CASE_MATCH_THRESHOLD:
            continue

        exclusions = await get_active_exclusions(match["matched_fir_id"])
        # If an accused is defined, check if they are excluded from the matched FIR
        accused_id = match.get("accused_id")
        if accused_id and accused_id in exclusions:
            print(f"[ColdCaseMatcher] Suppressing match between {fir_id} and {match['matched_fir_id']} for accused {accused_id} due to active exclusion.")
            continue

        item = ReviewQueueItem(
            item_id=str(uuid.uuid4()),
            item_type="cold_case_match",
            fir_id=fir_id,
            related_fir_id=match["matched_fir_id"],
            accused_id=accused_id,
            summary=(f"New FIR {crime_no} shares MO similarity "
                     f"({match['score']:.0%}) with unsolved case "
                     f"{match['matched_fir_crime_no']}"),
            score=match["score"],
            created_date=datetime.now(timezone.utc).isoformat(),
        )
        await push_review_item(item)
        print(f"[ColdCaseMatcher] Generated ReviewQueueItem alert {item.item_id} for match: {crime_no} -> {match['matched_fir_crime_no']}.")

async def compute_and_run_cold_case_match(fir: dict):
    """
    1. Runs semantic search against Catalyst KB to find modus operandi matches.
    2. Writes SHARED_MO derived relationships in Memgraph.
    3. Runs cold case matcher to generate alerts.
    """
    fir_id = fir.get("fir_internal_id")
    if not fir_id:
        return

    # Use MO descriptor if available, otherwise fallback to narrative
    query_text = fir.get("mo_descriptor") or fir.get("narrative") or ""
    if not query_text.strip():
        print(f"[ColdCaseMatcher] No MO descriptor or narrative for FIR {fir_id}. Skipping matching.")
        return

    content_query = f"NARRATIVE: {fir.get('narrative', '')}\nMO DESCRIPTOR: {fir.get('mo_descriptor', '')}"
    
    try:
        search_resp = await kb_search(content_query, top_k=20)
    except Exception as e:
        print(f"[ColdCaseMatcher] KB search failed for FIR {fir_id}: {e}")
        return

    shared_mo_matches = []
    
    for hit in search_resp.get("results", []):
        matched_fir_id = hit.get("fir_id") or hit.get("document_id") or hit.get("id")
        if not matched_fir_id or matched_fir_id == fir_id:
            continue
            
        score = hit.get("score") or hit.get("relevance") or hit.get("similarity", 0.0)
        if score < COLD_CASE_MATCH_THRESHOLD:
            continue
            
        # Get matched FIR details
        cypher = """
        MATCH (f:FIR {id: $id})
        OPTIONAL MATCH (a:Accused)-[:ACCUSED_IN]->(f)
        RETURN f.status as status, f.crime_no as crime_no, collect(a.id) as accused_ids
        """
        try:
            graph_res = await run_query(cypher, {"id": matched_fir_id})
        except Exception as e:
            print(f"[ColdCaseMatcher] Failed to query details for matched FIR {matched_fir_id}: {e}")
            continue

        if not graph_res:
            continue
            
        matched_fir_status = graph_res[0].get("status") or "open"
        matched_fir_crime_no = graph_res[0].get("crime_no") or ""
        
        # Write derived SHARED_MO relationship in graph
        edge_id = f"SHARED_MO_{fir_id}_{matched_fir_id}"
        try:
            await run_write("""
                MATCH (f1:FIR {id: $f1_id}), (f2:FIR {id: $f2_id})
                MERGE (f1)-[r:SHARED_MO]->(f2)
                SET r.score = $score, r.edge_id = $edge_id, r.edge_type = 'SHARED_MO'
            """, {
                "f1_id": fir_id,
                "f2_id": matched_fir_id,
                "score": score,
                "edge_id": edge_id
            })
        except Exception as e:
            print(f"[ColdCaseMatcher] Failed to write SHARED_MO edge: {e}")

        # Construct matches for cold-case matcher filter
        new_accused_ids = fir.get("accused_ids") or []
        if new_accused_ids:
            for accused_id in new_accused_ids:
                shared_mo_matches.append({
                    "matched_fir_id": matched_fir_id,
                    "matched_fir_status": matched_fir_status,
                    "score": score,
                    "accused_id": accused_id,
                    "matched_fir_crime_no": matched_fir_crime_no
                })
        else:
            shared_mo_matches.append({
                "matched_fir_id": matched_fir_id,
                "matched_fir_status": matched_fir_status,
                "score": score,
                "accused_id": None,
                "matched_fir_crime_no": matched_fir_crime_no
            })

    # Run the filtering and queue alert pushes
    if shared_mo_matches:
        await run_cold_case_match(fir, shared_mo_matches)
