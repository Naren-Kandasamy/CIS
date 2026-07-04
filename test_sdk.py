import zcatalyst_sdk
import os
from dotenv import load_dotenv

load_dotenv()

if not os.getenv("CATALYST_API_TOKEN"):
    raise EnvironmentError("CATALYST_API_TOKEN is not set")
os.environ.setdefault("CATALYST_PROJECT_ID", "45958000000015001")

try:
    app = zcatalyst_sdk.initialize(req=None)
    zcql = app.zcql()
    print("SDK Initialized!")
except Exception as e:
    print(f"Error: {e}")
