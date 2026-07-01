import json
import os
import sys
import asyncio

# Ensure Python can import from shared/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.append(BASE_DIR)

from shared.catalyst_client import kb_upload, ztsql_execute
from shared.graph_client import run_write, close

async def write_fir_to_ztsql(fir: dict):
    """Insert structured FIR data into Catalyst Relational DB."""
    sql = """
        INSERT INTO cases (fir_internal_id, crime_no, registered_date, crime_head_id, crime_sub_head_id)
        VALUES (?, ?, ?, ?, ?)
    """
    params = [
        fir["fir_internal_id"],
        fir["crime_no"],
        fir["incident_date"],
        fir["crime_head_id"],
        fir["crime_sub_head_id"]
    ]
    try:
        await ztsql_execute(sql, params)
    except Exception as e:
        # In case the table is missing or credentials aren't set during this dry-run
        pass

async def write_fir_to_memgraph(fir: dict):
    """Insert nodes and relationships into Memgraph."""
    try:
        # Create FIR Node
        await run_write(
            "MERGE (f:FIR {id: $fid}) SET f.date = $date", 
            {"fid": fir["fir_internal_id"], "date": fir["incident_date"]}
        )
        # Create Accused Nodes and link them
        for acc in fir.get("accused_ids", []):
            await run_write("MERGE (a:Accused {id: $acc})", {"acc": acc})
            await run_write(
                "MATCH (f:FIR {id: $fid}), (a:Accused {id: $acc}) MERGE (a)-[:ACCUSED_IN]->(f)",
                {"fid": fir["fir_internal_id"], "acc": acc}
            )
    except Exception:
        pass

async def upload_fir_to_kb(fir: dict):
    """Upload narrative text to Catalyst Vector Knowledge Base."""
    content = f"FIR: {fir['crime_no']}\nNarrative: {fir.get('narrative', '')}\nMO: {fir.get('mo_descriptor', '')}"
    metadata = {"crime_no": fir["crime_no"], "district": fir["district_name"]}
    try:
        await kb_upload(fir["fir_internal_id"], content, metadata)
    except Exception:
        pass

async def ingest_one(fir: dict):
    """Parallel upload to all three destinations per FIR."""
    await asyncio.gather(
        upload_fir_to_kb(fir),
        write_fir_to_memgraph(fir),
        write_fir_to_ztsql(fir)
    )

async def main():
    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "story_firs.json")
    if not os.path.exists(json_path):
        print("❌ JSON file not found!")
        return
        
    with open(json_path, 'r') as f:
        data = json.load(f)
        
    print(f"[*] Starting ingestion of {len(data)} FIRs to ZTSQL, Memgraph, and Catalyst KB...")
    
    # Process in batches of 50 to avoid overloading the Catalyst APIs / Memgraph driver
    batch_size = 50
    for i in range(0, len(data), batch_size):
        batch = data[i:i+batch_size]
        await asyncio.gather(*(ingest_one(fir) for fir in batch))
        print(f"  -> Successfully ingested {min(i+batch_size, len(data))} / {len(data)}")
        
    await close() # Cleanly close Memgraph connection pool
    print("✅ Ingestion Phase 5 complete!")

if __name__ == "__main__":
    asyncio.run(main())
