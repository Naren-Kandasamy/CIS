import asyncio
import sys
import os
import time

# Add root project directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.graph_client import run_query, close
from dotenv import load_dotenv

async def run_benchmark():
    print("🚀 Starting rigorous latency and accuracy benchmark on Cloud Database...")
    print(f"Connecting to: {os.getenv('MEMGRAPH_URI')}")
    
    # Test 1: Simple Count Query (Accuracy)
    start_time = time.perf_counter()
    res = await run_query("MATCH (f:FIR) RETURN count(f) as count")
    end_time = time.perf_counter()
    
    count = res[0]['count'] if res else 0
    latency = (end_time - start_time) * 1000
    print(f"\n[TEST 1] Total FIRs in Cloud: {count}")
    print(f"         Latency: {latency:.2f} ms")
    if count != 4000:
        print("❌ FAILED: Accuracy mismatch. Expected 4000 FIRs.")
    else:
        print("✅ PASSED: Data ingestion accuracy 100%.")

    # Test 2: Complex Multi-Hop Query (Latency)
    print("\n[TEST 2] Executing complex multi-hop crime ring analysis...")
    complex_query = """
    MATCH (a1:Accused)-[:ACCUSED_IN]->(f:FIR)<-[:ACCUSED_IN]-(a2:Accused)
    WHERE a1.id STARTS WITH 'ACC-STORY-' AND a1 <> a2
    RETURN a1.id as accused1, a2.id as accused2, f.district as district
    LIMIT 50
    """
    
    start_time = time.perf_counter()
    res = await run_query(complex_query)
    end_time = time.perf_counter()
    
    latency = (end_time - start_time) * 1000
    print(f"         Returned {len(res)} co-accused relationship rings.")
    print(f"         Latency: {latency:.2f} ms")
    if len(res) == 0:
        print("❌ FAILED: Could not retrieve planted story rings.")
    else:
        print("✅ PASSED: Complex reasoning graph query succeeded.")

    # Test 3: String Filtering on Narrative Property
    print("\n[TEST 3] Testing full-text parsing over narratives...")
    string_query = """
    MATCH (f:FIR)
    WHERE toLower(f.narrative) CONTAINS 'iron rod'
    RETURN count(f) as count
    """
    
    start_time = time.perf_counter()
    res = await run_query(string_query)
    end_time = time.perf_counter()
    
    latency = (end_time - start_time) * 1000
    count_iron = res[0]['count'] if res else 0
    print(f"         Found {count_iron} records containing 'iron rod'.")
    print(f"         Latency: {latency:.2f} ms")
    if count_iron == 0:
        print("❌ FAILED: Narrative properties missing or not searchable.")
    else:
        print("✅ PASSED: String property filtering successful.")

async def main():
    load_dotenv()
    try:
        await run_benchmark()
    finally:
        await close()
        print("\n🏁 Benchmark complete.")

if __name__ == "__main__":
    asyncio.run(main())
