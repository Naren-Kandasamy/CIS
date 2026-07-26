import asyncio
import aiohttp
import time
import json

# Replace with your deployed AppSail URL from the deploy logs
APPSAIL_URL = "https://backend-50043491738.development.catalystappsail.in"

async def generate_traffic():
    print(f"🚀 Starting APM Load Generator against {APPSAIL_URL}...")
    
    async with aiohttp.ClientSession() as session:
        # 1. Login to get a token
        print("Authenticating...")
        login_url = f"{APPSAIL_URL}/api/auth/login"
        async with session.post(login_url, json={"username": "dysp1", "password": "demo1234"}) as resp:
            if resp.status != 200:
                print(f"❌ Login failed! Status: {resp.status}")
                return
            
            data = await resp.json()
            token = data.get("token")
            print(f"✅ Logged in successfully. Token: {token[:10]}...")
            
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        # 2. Fire several queries to trigger the ps_1_cis_function
        queries = [
            "Are there any common links between the Majestic theft and the recent robbery in Jayanagar?",
            "Show me murder cases from last month in Indiranagar. I need this immediately.",
            "Check criminal history of Syed in Shivajinagar area",
            "What is the MO for the latest chain snatching incidents?",
            "Find associates of Ravi Kumar in Koramangala"
        ]
        
        print(f"\n📡 Firing {len(queries)} queries to populate APM...")
        for i, q in enumerate(queries):
            print(f"   [{i+1}/{len(queries)}] Sending query: '{q[:40]}...'")
            start_time = time.time()
            
            query_url = f"{APPSAIL_URL}/api/query"
            payload = {
                "session_id": f"apm-test-session-{i}",
                "query": q
            }
            
            async with session.post(query_url, json=payload, headers=headers) as resp:
                if resp.status == 200:
                    # We just consume the stream to let the backend finish
                    async for line in resp.content:
                        pass
                    elapsed = time.time() - start_time
                    print(f"   ✅ Finished in {elapsed:.1f}s")
                else:
                    print(f"   ❌ Query failed with status {resp.status}")
                    
        print("\n🏁 Traffic generation complete! Wait 60 seconds and refresh the APM dashboard.")

if __name__ == "__main__":
    asyncio.run(generate_traffic())
