import asyncio, aiohttp, time
APPSAIL_URL = "https://backend-50043491738.development.catalystappsail.in"
async def main():
    async with aiohttp.ClientSession() as session:
        resp = await session.post(f"{APPSAIL_URL}/api/auth/login", json={"username": "dysp1", "password": "demo1234"})
        token = (await resp.json()).get("token")
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        payload = {"session_id": "test-500-session", "query": "Find associates of Ravi Kumar in Koramangala"}
        print("Sending...")
        async with session.post(f"{APPSAIL_URL}/api/query", json=payload, headers=headers) as r:
            print("Status:", r.status)
            if r.status != 200:
                print(await r.text())
asyncio.run(main())
