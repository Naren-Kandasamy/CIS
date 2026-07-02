import asyncio
from dotenv import load_dotenv
load_dotenv()
from shared.graph_client import run_query

async def main():
    q = """
    MATCH (f:FIR)
    WHERE toLower(f.crime_type) CONTAINS 'murder' AND toLower(f.district) CONTAINS 'mysuru'
    RETURN f.id as fir_id
    LIMIT 10
    """
    res = await run_query(q)
    print(f"Found {len(res)} FIRs")
    if not res: return
    
    fir_ids = [r['fir_id'] for r in res]
    fir_list_str = "[" + ", ".join([f"'{fid}'" for fid in fir_ids]) + "]"
    
    q2 = f"""
    MATCH (p:Person)-[r]->(f:FIR)
    WHERE f.id IN {fir_list_str}
    RETURN p.id as person_id, type(r) as rel_type, f.id as fir_id
    """
    res2 = await run_query(q2)
    print(f"Found {len(res2)} associated Persons")
    
asyncio.run(main())
