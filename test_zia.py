import asyncio
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import translate_text, _get_nosql_access_token

async def test():
    try:
        res = await translate_text("This is a test", "en", "kn")
        print("Zia Translation Success!")
        print(res)
    except Exception as e:
        print(f"Error: {e}")
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            print(f"Status: {e.response.status_code}")
            print(f"Body: {e.response.text}")

asyncio.run(test())
