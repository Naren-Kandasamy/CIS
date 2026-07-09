from contextlib import asynccontextmanager
from fastapi import FastAPI

# BUG FIX: nothing previously loaded .env for the backend process itself --
# only start_all.sh's manual `export $(grep ...)` did, which is fragile/shell-
# specific and skipped entirely if uvicorn is run directly (as Catalyst's own
# "run_command" does). load_dotenv() is a no-op in real deployment (no .env
# file there; Catalyst injects env vars directly).
from dotenv import load_dotenv
load_dotenv()

from backend.api.routes import query, health, transcribe, graph, tts, ocr, export, auth
from backend.api.middleware.input_validator import InputValidationMiddleware
from backend.api.middleware.rbac import RBACMiddleware
from fastapi.middleware.cors import CORSMiddleware

async def init_nosql_client():
    pass

async def close_nosql_client():
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lightweight -- just confirm NoSQL client + Signals publisher URL are configured.
    # No Memgraph handshake, no LLM ping -- those now live in pipeline_function/.
    await init_nosql_client()
    yield
    await close_nosql_client()
    # BUG-05 FIX: close the Memgraph driver on app shutdown to release
    # the connection pool back to Memgraph instead of leaking it.
    from shared.graph_client import close as close_graph_driver
    await close_graph_driver()

app = FastAPI(lifespan=lifespan)

import os

ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(InputValidationMiddleware)
app.add_middleware(RBACMiddleware)
# BUG FIX: Catalyst's own AppSail gateway independently reflects the request's
# Origin header on every response (confirmed via x-frame-options: ALLOW-FROM
# <origin>, which this app never sets) -- adding our own CORSMiddleware on top
# produced two Access-Control-Allow-Origin/-Credentials values on the same
# response, which browsers reject as invalid, breaking every cross-origin call.
# X_ZOHO_CATALYST_LISTEN_PORT is only set when actually running inside
# Catalyst's AppSail, never during local dev, where there's no gateway to
# reflect Origin and this middleware is still needed.
if not os.getenv("X_ZOHO_CATALYST_LISTEN_PORT"):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(query.router)
app.include_router(health.router)
app.include_router(transcribe.router)
app.include_router(graph.router)
app.include_router(tts.router)
app.include_router(ocr.router)
app.include_router(export.router)
app.include_router(auth.router)
