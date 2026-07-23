import asyncio
from shared.catalyst_client import ztsql_query
async def main():
    try:
        # Check if cases table exists by doing a basic select
        res = await ztsql_query("SELECT * FROM cases LIMIT 1")
        print("Cases table query result:", res)
    except Exception as e:
        print("Cases table error:", e)
        
    try:
        # Check if Firs table exists (old table)
        res2 = await ztsql_query("SELECT * FROM Firs LIMIT 1")
        print("Firs table query result:", res2)
    except Exception as e:
        print("Firs table error:", e)
        
asyncio.run(main())
