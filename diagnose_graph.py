import asyncio
from dotenv import load_dotenv
load_dotenv()
from shared.graph_client import run_query

async def main():
    # The real property names are: crime_no, date, district, id
    # Let's verify all actual keys in FIR nodes
    full_sample = await run_query("MATCH (f:FIR) RETURN f LIMIT 3")
    print("=== FULL FIR DATA (all properties) ===")
    for row in full_sample:
        print(row['f'])
        print("---")
    
    # Count Belagavi
    belagavi_count = await run_query("""
        MATCH (f:FIR)
        WHERE f.district = 'Belagavi'
        RETURN count(f) as cnt
    """)
    print("\n=== BELAGAVI COUNT ===", belagavi_count)

    # Get a full Belagavi FIR
    belagavi_sample = await run_query("""
        MATCH (f:FIR)
        WHERE f.district = 'Belagavi'
        RETURN f LIMIT 2
    """)
    print("\n=== BELAGAVI FIR FULL PROPS ===")
    for row in belagavi_sample:
        print(row['f'])

asyncio.run(main())
