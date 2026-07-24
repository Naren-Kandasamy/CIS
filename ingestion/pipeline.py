import asyncio
import json
import logging
import os
import sys

# Add root project directory to path so imports work correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from shared.catalyst_client import kb_upload, ztsql_execute
from shared.graph_client import run_write, close

logger = logging.getLogger(__name__)

# LOCAL DEV MODE FLAG
# If Catalyst env vars aren't present, simulate ingestion so the script completes
LOCAL_MOCK_MODE = not os.getenv("CATALYST_API_TOKEN")

async def ingest_fir_to_kb(fir: dict, sem: asyncio.Semaphore):
    async with sem:
        if LOCAL_MOCK_MODE:
            await asyncio.sleep(0.01)
            return
            
        content = f"NARRATIVE: {fir.get('narrative', '')}\nMO DESCRIPTOR: {fir.get('mo_descriptor', '')}"
        # BUG FIX: metadata previously only had "crime_sub_head" and no date
        # field at all, while the dashboard visualization (building_visualization_node)
        # reads "crime_type" and "Date" -- KB/RAG-sourced evidence was silently
        # bucketed as "Unknown" with no date. crime_type/Date are added here to
        # match the key names the graph-sourced path already produces.
        metadata = {
            "fir_id": fir["fir_internal_id"],
            "crime_no": fir.get("crime_no", ""),
            "district": fir.get("district_name", ""),
            "crime_sub_head": fir.get("crime_sub_head_name", ""),
            "crime_type": fir.get("crime_sub_head_name", ""),
            "Date": fir.get("incident_date", ""),
            "ocr_extracted": fir.get("ocr_extracted", False)
        }
        try:
            await kb_upload(fir["fir_internal_id"], content, metadata)
        except Exception as e:
            # We catch and log so one failure doesn't crash the entire batch
            logger.error(f"KB upload failed for {fir['fir_internal_id']}: {e}")

async def ingest_fir_to_sql(fir: dict, sem: asyncio.Semaphore):
    async with sem:
        if LOCAL_MOCK_MODE:
            await asyncio.sleep(0.01)
            return
            
        # BUG FIX: previously targeted a table "Firs" with columns
        # (fir_internal_id, crime_no, district_name, incident_date,
        # crime_sub_head_name) -- a table nothing else in the codebase reads
        # from. The actual retrieval code (sql_client.py) and the other real
        # seeding scripts (data/scripts/ingest_all.py, plant_trap_scenario.py)
        # all target "cases" with (fir_internal_id, crime_no, registered_date,
        # crime_head_id, crime_sub_head_id). Aligned to match.
        sql = """
        INSERT INTO cases (fir_internal_id, crime_no, registered_date, crime_head_id, crime_sub_head_id)
        VALUES (?, ?, ?, ?, ?)
        """
        params = [
            fir["fir_internal_id"], fir.get("crime_no", ""), fir.get("incident_date", ""),
            fir.get("crime_head_id", ""), fir.get("crime_sub_head_id", "")
        ]
        try:
            await ztsql_execute(sql, params)
        except Exception as e:
            logger.error(f"SQL insert failed for {fir['fir_internal_id']}: {e}")

async def ingest_fir_to_graph(fir: dict, sem: asyncio.Semaphore):
    async with sem:
        cypher = """
        MERGE (f:FIR {id: $fir_id})
        SET f.crime_no = $crime_no, 
            f.district = $district, 
            f.date = $date,
            f.crime_type = $crime_type,
            f.modus_operandi = $modus_operandi,
            f.weapon = $weapon,
            f.ps_name = $ps_name,
            f.narrative = $narrative,
            f.status = $status
        """
        params = {
            "fir_id": fir["fir_internal_id"],
            "crime_no": fir.get("crime_no", ""),
            "district": fir.get("district_name", ""),
            "date": fir.get("incident_date", ""),
            "crime_type": fir.get("crime_sub_head_name", ""),
            "modus_operandi": fir.get("mo_descriptor", ""),
            "weapon": fir.get("weapon", ""),
            "ps_name": fir.get("ps_name", ""),
            "narrative": fir.get("narrative", ""),
            "status": fir.get("status", "open")
        }
        try:
            await run_write(cypher, params)
            
            # Relate Accused
            for accused_id in fir.get("accused_ids", []):
                rel_cypher = """
                MATCH (f:FIR {id: $fir_id})
                MERGE (a:Accused {id: $accused_id})
                MERGE (a)-[:ACCUSED_IN]->(f)
                """
                await run_write(rel_cypher, {"fir_id": fir["fir_internal_id"], "accused_id": accused_id})
                
            # Relate Victims
            for victim_id in fir.get("victim_ids", []):
                rel_cypher = """
                MATCH (f:FIR {id: $fir_id})
                MERGE (v:Victim {id: $victim_id})
                MERGE (v)-[:VICTIM_IN]->(f)
                """
                await run_write(rel_cypher, {"fir_id": fir["fir_internal_id"], "victim_id": victim_id})
        except Exception as e:
            logger.error(f"Graph insert failed for {fir['fir_internal_id']}: {e}")

async def run_ingestion_pipeline():
    logger.info("Starting offline ingestion pipeline...")
    if LOCAL_MOCK_MODE:
        logger.warning("No CATALYST_API_TOKEN found. Running in LOCAL MOCK MODE! APIs will not actually be called.")
    
    file_path = os.path.join(os.path.dirname(__file__), "../data/story_firs.json")
    with open(file_path, "r") as f:
        firs = json.load(f)
        
    logger.info(f"Loaded {len(firs)} FIRs from data/story_firs.json")
    
    # Use semaphores to prevent overwhelming the APIs
    # Keeping concurrency reasonable so we don't hit Catalyst API rate limits
    kb_sem = asyncio.Semaphore(15)
    sql_sem = asyncio.Semaphore(15)
    graph_sem = asyncio.Semaphore(15)
    
    logger.info("Building ingestion tasks...")
    # For massive datasets, we process in chunks to prevent memory bloat in asyncio
    chunk_size = 500
    try:
        for i in range(0, len(firs), chunk_size):
            chunk = firs[i:i+chunk_size]
            chunk_tasks = []
            for fir in chunk:
                chunk_tasks.append(ingest_fir_to_kb(fir, kb_sem))
                chunk_tasks.append(ingest_fir_to_sql(fir, sql_sem))
                chunk_tasks.append(ingest_fir_to_graph(fir, graph_sem))
            
            logger.info(f"Executing chunk {i//chunk_size + 1}... ({len(chunk)} FIRs)")
            await asyncio.gather(*chunk_tasks)
            logger.info(f"Finished ingestion for chunk {i//chunk_size + 1}. Running cold-case matching...")
            
            from ingestion.cold_case_matcher import compute_and_run_cold_case_match
            match_tasks = []
            for fir in chunk:
                match_tasks.append(compute_and_run_cold_case_match(fir))
            await asyncio.gather(*match_tasks)
            logger.info(f"Finished cold-case matching for chunk {i//chunk_size + 1}.")
    finally:
        await close()
        logger.info("Ingestion complete.")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_ingestion_pipeline())
