import asyncio
import json
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.graph_client import run_write, run_query, close

logger = logging.getLogger(__name__)

async def create_constraints():
    logger.info("Creating Memgraph constraints and indices...")
    commands = [
        "CREATE CONSTRAINT ON (f:FIR) ASSERT f.id IS UNIQUE",
        "CREATE CONSTRAINT ON (a:Accused) ASSERT a.id IS UNIQUE",
        "CREATE CONSTRAINT ON (v:Victim) ASSERT v.id IS UNIQUE",
        "CREATE INDEX ON :FIR(crime_no)",
        "CREATE INDEX ON :FIR(district)"
    ]
    for cmd in commands:
        try:
            await run_write(cmd, {})
            logger.info(f"Executed: {cmd}")
        except Exception as e:
            if "already exists" in str(e).lower():
                logger.info(f"Skipped (already exists): {cmd}")
            else:
                logger.error(f"Failed to execute {cmd}: {e}")

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
            f.narrative = $narrative
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
            "narrative": fir.get("narrative", "")
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

async def run_graph_hydration():
    # Verify connection
    try:
        await run_query("RETURN 1 AS test")
        logger.info("✅ Connected to Memgraph successfully.")
    except Exception as e:
        logger.error(f"❌ Failed to connect to Memgraph. Check MEMGRAPH_URI in .env. Error: {e}")
        return

    await create_constraints()

    file_path = os.path.join(os.path.dirname(__file__), "../story_firs.json")
    with open(file_path, "r") as f:
        firs = json.load(f)
        
    logger.info(f"Loaded {len(firs)} FIRs. Starting Graph hydration...")
    
    graph_sem = asyncio.Semaphore(100) # Memgraph can handle high concurrency
    
    chunk_size = 500
    try:
        for i in range(0, len(firs), chunk_size):
            chunk = firs[i:i+chunk_size]
            chunk_tasks = [ingest_fir_to_graph(fir, graph_sem) for fir in chunk]
            
            logger.info(f"Executing chunk {i//chunk_size + 1}... ({len(chunk)} FIRs)")
            await asyncio.gather(*chunk_tasks)
            
    finally:
        await close()
        logger.info("✅ Graph hydration complete.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    asyncio.run(run_graph_hydration())
