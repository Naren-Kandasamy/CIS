import asyncio
import os
from dotenv import load_dotenv

# Load current env to get client id, secret, refresh token
load_dotenv()

from shared.catalyst_client import _get_nosql_access_token

async def main():
    token = await _get_nosql_access_token()
    print(f"Got fresh token: {token[:10]}...")
    
    # Update .env file
    env_path = "/home/nkandasamy/Desktop/CIS/.env"
    with open(env_path, 'r') as f:
        lines = f.readlines()
        
    with open(env_path, 'w') as f:
        for line in lines:
            if line.startswith("CATALYST_API_TOKEN="):
                f.write(f'CATALYST_API_TOKEN="{token}"\n')
            else:
                f.write(line)
    print("Updated .env with fresh CATALYST_API_TOKEN")

asyncio.run(main())
