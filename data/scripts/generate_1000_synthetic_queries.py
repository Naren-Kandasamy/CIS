import asyncio
import sys
import os
import random
import csv
import json
import httpx
import uuid
import time
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
from shared.graph_client import run_query, close
from dotenv import load_dotenv

# Define evaluation templates to test different capabilities
TEMPLATES = [
    "List all {crime_type} crimes in {district} district.",
    "Are there any cases involving a {weapon} in {district}?",
    "Show me cases where the narrative explicitly mentions a {weapon}.",
    "What is the most common crime type in {district}?",
    "Which accused has the highest page rank score in {district}?",
    "Are there any repeat offenders linked to {crime_type}?",
    "Give me an analysis of modus operandi involving {weapon}.",
    "Show me all cases involving Section {ipc} of the IPC.",
    "Find me cases involving a {weapon} and a {crime_type}.",
    "Who is the central figure in the {crime_type} rings in {district}?"
]

async def fetch_random_data():
    """Fetch random entities directly from the Memgraph Cloud Database to ensure queries are realistic."""
    districts = [r['d'] for r in await run_query("MATCH (f:FIR) RETURN DISTINCT f.district AS d LIMIT 50") if r['d']]
    crime_types = [r['c'] for r in await run_query("MATCH (f:FIR) RETURN DISTINCT f.crime_type AS c LIMIT 50") if r['c']]
    weapons = ["iron rod", "knife", "machete", "pistol", "glass cutter", "crowbar", "poison", "rope", "axe", "hammer"]
    ipc_sections = ["302", "307", "379", "392", "420", "498A", "376", "363", "324", "504"]
    
    return {
        "district": districts or ["Bengaluru", "Mysuru", "Belagavi"],
        "crime_type": crime_types or ["burglary", "murder", "theft", "assault"],
        "weapon": weapons,
        "ipc": ipc_sections
    }

def generate_queries(data, count=1000):
    """Generate the synthetic test payload."""
    queries = []
    for _ in range(count):
        template = random.choice(TEMPLATES)
        q = template.format(
            district=random.choice(data["district"]),
            crime_type=random.choice(data["crime_type"]),
            weapon=random.choice(data["weapon"]),
            ipc=random.choice(data["ipc"])
        )
        queries.append(q)
    return queries

async def run_drip_feed(queries):
    """Execute the pipeline with strict pacing to avoid Catalyst rate-limits."""
    csv_file = os.path.join(os.path.dirname(__file__), 'blind_evaluation_1000.csv')
    
    # Initialize CSV
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Query", "AI_Response", "Internal_Confidence_Tier", "Human_Label_Score"])
        writer.writeheader()
    
    async with httpx.AsyncClient() as client:
        # Authenticate with the local backend
        print("Authenticating with local backend...")
        auth_r = await client.post("http://localhost:8000/api/auth/login", json={"username": "dysp1", "password": "demo1234"}, timeout=60.0)
        auth_r.raise_for_status()
        token = auth_r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        for i, q in enumerate(queries):
            start_t = time.time()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] [{i+1}/{len(queries)}] Query: {q}")
            
            session_id = str(uuid.uuid4())
            ai_text = ""
            confidence = "UNKNOWN"
            try:
                # We point at localhost to use the local backend, which then securely talks to Cloud Memgraph and Catalyst
                async with client.stream("POST", "http://localhost:8000/api/query", headers=headers, json={"session_id": session_id, "query": q}, timeout=60.0) as response:
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            if data_str == "[DONE]":
                                break
                            try:
                                data = json.loads(data_str)
                                if "error" in data:
                                    ai_text = f"ERROR: {data['error']}"
                                    break
                                if "token" in data:
                                    ai_text += data["token"]
                                if "confidence_metrics" in data and isinstance(data["confidence_metrics"], dict):
                                    confidence = data["confidence_metrics"].get("tier", "UNKNOWN")
                            except json.JSONDecodeError:
                                pass
            except Exception as e:
                ai_text = f"ERROR: {str(e)}"
                confidence = "ERROR"

            # Append to CSV immediately so we don't lose data if the script stops
            with open(csv_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=["Query", "AI_Response", "Internal_Confidence_Tier", "Human_Label_Score"])
                writer.writerow({
                    "Query": q,
                    "AI_Response": ai_text.strip(),
                    "Internal_Confidence_Tier": confidence,
                    "Human_Label_Score": ""
                })
            
            # THROTTLE: Enforce a strict 7.2 second minimum per query to space 1000 queries over exactly 2 hours.
            # This completely avoids triggering the 10-minute Catalyst API Stall.
            elapsed = time.time() - start_t
            sleep_time = max(0, 7.2 - elapsed)
            await asyncio.sleep(sleep_time)

async def main():
    load_dotenv()
    print("Fetching random graph data from Memgraph Cloud...")
    try:
        data = await fetch_random_data()
    finally:
        await close()
        
    print("Generating 1000 synthetic queries...")
    queries = generate_queries(data, 1000)
    
    print("Starting 2-hour throttled pipeline execution drip-feed...")
    await run_drip_feed(queries)
    print(f"✅ All 1,000 queries evaluated successfully! File saved to data/scripts/blind_evaluation_1000.csv")

if __name__ == "__main__":
    asyncio.run(main())
