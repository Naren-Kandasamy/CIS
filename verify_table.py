import asyncio
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import ztsql_query

async def main():
    try:
        # Check if cases table exists by doing a basic select
        res = await ztsql_query("SELECT * FROM cases LIMIT 1")
        print("SUCCESS! cases table query result:", res)
    except Exception as e:
        print("ERROR cases table error:", e)

asyncio.run(main())
