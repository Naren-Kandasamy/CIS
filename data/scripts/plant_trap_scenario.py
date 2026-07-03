import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from shared.catalyst_client import kb_upload, ztsql_execute
from shared.graph_client import run_write, close

trap_firs = [
    {
        "fir_internal_id": "TRAP-FIR-001",
        "crime_no": "199991234202100001",
        "district_name": "Belagavi",
        "incident_date": "2021-04-15",
        "crime_head_id": "CH002",
        "crime_sub_head_id": "CSH004",
        "crime_sub_head_name": "Burglary",
        "accused_ids": ["TRAP-ACC-001"],
        "mo_descriptor": "The suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face.",
        "narrative": "A burglary occurred in Belagavi where the suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face."
    },
    {
        "fir_internal_id": "TRAP-FIR-002",
        "crime_no": "199995678202400002",
        "district_name": "Kalaburagi",
        "incident_date": "2024-08-20",
        "crime_head_id": "CH002",
        "crime_sub_head_id": "CSH004",
        "crime_sub_head_name": "Burglary",
        "accused_ids": ["TRAP-ACC-002"],
        "mo_descriptor": "The suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face.",
        "narrative": "A burglary occurred in Kalaburagi where the suspect broke in through the rear window using a specialized glass cutter and left a calling card with a smiley face."
    }
]

async def plant_trap_scenario():
    print("Planting trap scenario (2 disconnected FIRs with identical MO)...")
    for fir in trap_firs:
        # ZTSQL
        sql = """
            INSERT INTO cases (fir_internal_id, crime_no, registered_date, crime_head_id, crime_sub_head_id)
            VALUES (?, ?, ?, ?, ?)
        """
        params = [fir["fir_internal_id"], fir["crime_no"], fir["incident_date"], fir["crime_head_id"], fir["crime_sub_head_id"]]
        try:
            await ztsql_execute(sql, params)
        except Exception:
            pass # ignore if it already exists

        # Graph
        await run_write(
            "MERGE (f:FIR {id: $fid}) SET f.date = $date, f.district = $district", 
            {"fid": fir["fir_internal_id"], "date": fir["incident_date"], "district": fir["district_name"]}
        )
        for acc in fir["accused_ids"]:
            await run_write("MERGE (a:Accused {id: $acc})", {"acc": acc})
            await run_write(
                "MATCH (f:FIR {id: $fid}), (a:Accused {id: $acc}) MERGE (a)-[:ACCUSED_IN]->(f)",
                {"fid": fir["fir_internal_id"], "acc": acc}
            )

        # KB
        content = f"FIR: {fir['crime_no']}\\nNarrative: {fir['narrative']}\\nMO: {fir['mo_descriptor']}"
        metadata = {"crime_no": fir["crime_no"], "district": fir["district_name"]}
        try:
            await kb_upload(fir["fir_internal_id"], content, metadata)
        except Exception:
            pass
            
    print("✅ Trap scenario planted successfully.")

async def main():
    try:
        await plant_trap_scenario()
    finally:
        await close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
