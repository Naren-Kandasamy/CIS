from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.api.routes import query, health, transcribe, graph, tts, ocr, export
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

app = FastAPI(lifespan=lifespan)

import os

ALLOWED_ORIGINS = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
).split(",")

app.add_middleware(InputValidationMiddleware)
app.add_middleware(RBACMiddleware)
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
