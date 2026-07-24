import asyncio
import os
from dotenv import load_dotenv
load_dotenv()
from shared.catalyst_client import ztsql_execute

async def setup():
    create_sql = """
    CREATE TABLE cases (
        fir_internal_id VARCHAR(255) PRIMARY KEY,
        crime_no VARCHAR(255),
        registered_date VARCHAR(255),
        crime_head_id VARCHAR(255),
        crime_sub_head_id VARCHAR(255),
        narrative_language VARCHAR(8),
        narrative_original VARCHAR(2000),
        narrative_is_translated BOOLEAN DEFAULT FALSE,
        mo_descriptor_language VARCHAR(8),
        mo_descriptor_original VARCHAR(2000),
        mo_descriptor_is_translated BOOLEAN DEFAULT FALSE
    )
    """
    print("Executing CREATE TABLE...")
    try:
        await ztsql_execute(create_sql)
        print("Done!")
    except Exception as e:
        print(f"Error: {e}")

asyncio.run(setup())
