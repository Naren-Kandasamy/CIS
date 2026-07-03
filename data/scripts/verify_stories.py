import asyncio
import sys
import os

# Add root project directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.graph_client import run_query, close

async def verify_stories():
    print("Verifying planted stories in the graph database...")
    
    # 1. Check if the 50 planted accused exist
    query_accused = """
    MATCH (a:Accused)
    WHERE a.id STARTS WITH 'ACC-STORY-'
    RETURN count(a) as count
    """
    res = await run_query(query_accused)
    accused_count = res[0]['count'] if res else 0
    print(f"Planted Accused count: {accused_count} (Expected: 50)")
    
    # 2. Check their links to FIRs
    query_links = """
    MATCH (a:Accused)-[r:ACCUSED_IN]->(f:FIR)
    WHERE a.id STARTS WITH 'ACC-STORY-'
    RETURN count(r) as count
    """
    res = await run_query(query_links)
    links_count = res[0]['count'] if res else 0
    print(f"Accused-FIR links: {links_count} (Expected: > 500)")
    
    # 3. Check MAGE metrics on these nodes (PageRank and Centrality)
    query_mage = """
    MATCH (a:Accused)
    WHERE a.id STARTS WITH 'ACC-STORY-'
      AND a.page_rank_score IS NOT NULL 
      AND a.centrality_score IS NOT NULL
    RETURN count(a) as count
    """
    res = await run_query(query_mage)
    mage_count = res[0]['count'] if res else 0
    print(f"Accused with MAGE scores: {mage_count} (Expected: 50)")
    
    # Validation logic
    passed = True
    if accused_count < 50:
        print("❌ FAILED: Planted accused count mismatch.")
        passed = False
    if links_count < 500:
        print("❌ FAILED: Not enough links to planted FIRs.")
        passed = False
    if mage_count < 50:
        print("❌ FAILED: MAGE scores are missing from some planted accused. Did you run run_mage_algorithms.py?")
        passed = False
        
    if passed:
        print("✅ ALL STORY VERIFICATIONS PASSED!")
    else:
        print("❌ SOME VERIFICATIONS FAILED!")
        sys.exit(1)
        
async def main():
    try:
        await verify_stories()
    finally:
        await close()

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
