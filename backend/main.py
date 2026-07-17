from contextlib import asynccontextmanager
from fastapi import FastAPI

# BUG FIX: nothing previously loaded .env for the backend process itself --
# only start_all.sh's manual `export $(grep ...)` did, which is fragile/shell-
# specific and skipped entirely if uvicorn is run directly (as Catalyst's own
# "run_command" does). load_dotenv() is a no-op in real deployment (no .env
# file there; Catalyst injects env vars directly).
from dotenv import load_dotenv
load_dotenv()

from backend.api.routes import query, health, transcribe, graph, tts, ocr, export, auth, exclusions, cases, sessions, translate, feedback, review_queue
from backend.api.middleware.input_validator import InputValidationMiddleware
from backend.api.middleware.rbac import RBACMiddleware
from fastapi.middleware.cors import CORSMiddleware

async def init_nosql_client():
    pass

async def close_nosql_client():
    pass

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup probes: print to DevOps Application logs ---
    # Check NoSQL auth first — if this fails every nosql_get/set will fail
    # silently and every query will hang in QUEUED state forever.
    try:
        from shared.catalyst_client import nosql_set, nosql_get
        await nosql_set("health:startup", "ok")
        result = await nosql_get("health:startup")
        print(f"[STARTUP] ✅ NoSQL health check passed: {result}")
    except Exception as e:
        print(f"[STARTUP] ❌ NoSQL health check FAILED — all queries will hang: {e}")

    # Check Signals URL — if missing, fallback inline runner is used which
    # may timeout long queries inside the AppSail event loop.
    signals_url = os.getenv("ZC_SIGNALS_PUBLISHER_URL") or os.getenv("CATALYST_SIGNALS_PUBLISHER_URL")
    if signals_url:
        print(f"[STARTUP] ✅ Signals URL is configured.")
    else:
        print(f"[STARTUP] ⚠️  ZC_SIGNALS_PUBLISHER_URL is NOT SET — pipeline will run inline (may timeout).")

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

# BUG FIX (defense-in-depth): allow_credentials=True combined with a literal
# "*" origin is invalid per the CORS spec, but Starlette's CORSMiddleware
# doesn't reject that combination -- it silently falls back to dynamically
# reflecting whatever Origin header the request sent, which is functionally
# "any site may make credentialed requests." The current default value is a
# safe, narrow allowlist, but nothing stops CORS_ALLOWED_ORIGINS from being
# set to "*" in some future deployment config by someone copying a "quick
# fix" pattern. Fail loudly instead of silently degrading into an open CORS
# policy.
if "*" in ALLOWED_ORIGINS:
    raise EnvironmentError(
        "CORS_ALLOWED_ORIGINS must not be '*' -- combined with allow_credentials=True "
        "this effectively allows any origin to make authenticated requests. "
        "List explicit origins instead."
    )

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
app.include_router(exclusions.router)
app.include_router(cases.router)
app.include_router(sessions.router)
app.include_router(translate.router)
app.include_router(feedback.router)
app.include_router(review_queue.router)
