import asyncio
import time
import os
import sys

# Add root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.graph_client import run_write, run_query, close

async def run_pagerank():
    print("Running PageRank algorithm...")
    start_time = time.time()
    # Run PageRank on Person nodes and their relationships
    # Memgraph MAGE algorithm: pagerank.get()
    
    # We will compute pagerank over the bipartite graph of Person-FIR
    query = """
    CALL pagerank.get()
    YIELD node, rank
    WITH node, rank
    WHERE "Accused" IN labels(node)
    SET node.page_rank_score = rank
    """
    try:
        await run_write(query)
        elapsed = time.time() - start_time
        print(f"✅ PageRank completed in {elapsed:.4f} seconds.")
    except Exception as e:
        print(f"❌ PageRank failed: {e}")

async def run_betweenness():
    print("Running Betweenness Centrality...")
    start_time = time.time()
    
    query = """
    CALL betweenness_centrality.get()
    YIELD node, betweenness_centrality
    WITH node, betweenness_centrality
    WHERE "Accused" IN labels(node)
    SET node.centrality_score = betweenness_centrality
    """
    try:
        await run_write(query)
        elapsed = time.time() - start_time
        print(f"✅ Betweenness Centrality completed in {elapsed:.4f} seconds.")
    except Exception as e:
        print(f"❌ Betweenness Centrality failed: {e}")

async def main():
    print("Starting MAGE algorithms execution on full graph...")
    
    # Test connection
    try:
        res = await run_query("MATCH (n) RETURN count(n) as c")
        print(f"Current graph node count: {res[0]['c']}")
    except Exception as e:
        print(f"Failed to connect to Memgraph: {e}")
        return
        
    await run_pagerank()
    await run_betweenness()
    
    await close()
    print("All algorithms finished.")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
