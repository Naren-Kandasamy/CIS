import zcatalyst_sdk
import os

os.environ["CATALYST_API_TOKEN"] = "m_1004.665d10ca35618d9bbd07ed5334861c45.13cbacb7119fece74c598b02a5b34922"
os.environ["CATALYST_PROJECT_ID"] = "45958000000015001"

try:
    app = zcatalyst_sdk.initialize(req=None)
    zcql = app.zcql()
    print("SDK Initialized!")
except Exception as e:
    print(f"Error: {e}")
