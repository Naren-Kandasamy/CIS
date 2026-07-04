import os
import uvicorn

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.environ["X_ZOHO_CATALYST_LISTEN_PORT"]))
