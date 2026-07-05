import zcatalyst_sdk
import asyncio

app = zcatalyst_sdk.initialize()
token = app._credential.get_access_token()
print("SDK Token:", token)
