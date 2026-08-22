import asyncio
import httpx

async def test_query():
    async with httpx.AsyncClient() as client:
        # Login
        print("Logging in...")
        resp = await client.post(
            "http://localhost:8001/api/auth/login",
            json={"username": "dysp1", "password": "demo1234"}
        )
        print("Login status:", resp.status_code)
        if resp.status_code != 200:
            print("Login failed:", resp.text)
            return
        
        token = resp.json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        
        # Query
        print("Submitting query...")
        import uuid
        session_id = str(uuid.uuid4())
        
        try:
            async with client.stream(
                "POST", 
                "http://localhost:8001/api/query", 
                headers=headers, 
                json={"session_id": session_id, "query": "Find murder cases involving a knife."},
                timeout=10.0
            ) as response:
                print("Query status:", response.status_code)
                async for chunk in response.aiter_text():
                    print("Event:", chunk.strip())
        except Exception as e:
            print("Error during stream:", e)

asyncio.run(test_query())
