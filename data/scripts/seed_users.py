import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from shared.auth import create_user

# Demo credentials spanning the KSP rank hierarchy, for local testing/demo day.
# Passwords are intentionally simple placeholders -- rotate before any real
# (non-demo) use.
DEMO_USERS = [
    {"username": "dysp1", "password": "demo1234", "role": "dysp", "display_name": "DySP Rao"},
    {"username": "inspector1", "password": "demo1234", "role": "inspector", "display_name": "Inspector Sharma"},
    {"username": "si1", "password": "demo1234", "role": "sub_inspector", "display_name": "SI Kumar"},
    {"username": "constable1", "password": "demo1234", "role": "constable", "display_name": "Constable Iyer"},
]

async def main():
    for u in DEMO_USERS:
        await create_user(u["username"], u["password"], u["role"], u["display_name"])
        print(f"Seeded user: {u['username']} ({u['role']})")
    print("Done. Demo password for all accounts: demo1234")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(main())
