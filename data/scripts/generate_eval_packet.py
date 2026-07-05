import asyncio
import csv
import sys
import os
import json
import httpx
import uuid

async def generate_packet():
    print("Generating Blind Evaluation Packet...")
    
    test_queries = [
        "Find me any cases involving a specialized glass cutter and a smiley face.",
        "List all crimes in Belagavi district.",
        "Are there any burglary cases involving an iron rod?",
        "Show me all cases involving Section 302 of the IPC.",
        "Which accused has the highest page rank score?",
        "Are there any repeat offenders linked to multiple FIRs?",
        "Give me an analysis of modus operandi involving window entries.",
        "What is the most common crime type in Kalaburagi?",
        "Who is the central figure in the drug trafficking ring?",
        "Show me cases where the narrative mentions a red getaway car."
    ]

    results = []
    
    async with httpx.AsyncClient() as client:
        # Authenticate first
        auth_r = await client.post("http://localhost:8000/api/auth/login", json={"username": "dysp1", "password": "demo1234"})
        auth_r.raise_for_status()
        token = auth_r.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        for i, q in enumerate(test_queries):
            print(f"[{i+1}/{len(test_queries)}] Processing query: {q}")
            session_id = str(uuid.uuid4())
            ai_text = ""
            confidence = "UNKNOWN"
            try:
                # The POST request directly returns an SSE stream
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
                                
                                if "content" in data:
                                    ai_text += data["content"]
                                    
                                if "visualization" in data and data["visualization"] and "confidence_metrics" in data["visualization"]:
                                    confidence = data["visualization"]["confidence_metrics"].get("tier", "UNKNOWN")
                            except json.JSONDecodeError:
                                pass
                
                results.append({
                    "Query": q,
                    "AI_Response": ai_text.strip(),
                    "Internal_Confidence_Tier": confidence
                })
            except Exception as e:
                print(f"Error on query '{q}': {e}")
                results.append({
                    "Query": q,
                    "AI_Response": f"ERROR: {str(e)}",
                    "Internal_Confidence_Tier": "ERROR"
                })

    # Save to CSV
    csv_file = os.path.join(os.path.dirname(__file__), 'blind_evaluation_packet.csv')
    with open(csv_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["Query", "AI_Response", "Internal_Confidence_Tier", "Human_Label_Score"])
        writer.writeheader()
        for r in results:
            r["Human_Label_Score"] = "" # Leave blank for Claude/Teammate to fill in
            writer.writerow(r)
            
    print(f"✅ Packet generated successfully: {csv_file}")

if __name__ == "__main__":
    asyncio.run(generate_packet())
