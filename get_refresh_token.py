import httpx
import os
from dotenv import load_dotenv, set_key

load_dotenv()
client_id = os.getenv("CATALYST_CLIENT_ID")
client_secret = os.getenv("CATALYST_CLIENT_SECRET")
grant_token = "1000.ea522125a54f7e31eb8a9d753324ea52.2ac59ac67365dbbeea951097cd042fdb"

r = httpx.post("https://accounts.zoho.in/oauth/v2/token", params={
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": grant_token,
})
data = r.json()
print(data)

if "refresh_token" in data:
    env_path = "/home/nkandasamy/Desktop/CIS/.env"
    set_key(env_path, "CATALYST_REFRESH_TOKEN", data["refresh_token"])
    if "access_token" in data:
        set_key(env_path, "CATALYST_API_TOKEN", data["access_token"])
    print("Tokens saved to .env!")
