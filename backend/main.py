from contextlib import asynccontextmanager
import os
from fastapi import FastAPI

# Loads .env for local runs -- start_all.sh's manual `export $(grep ...)` was
# fragile/shell-specific and skipped entirely when uvicorn is run directly (as
# Catalyst's own "run_command" does).
#
# BUG FIX: this used to run unconditionally, on the assumption that it was "a
# no-op in real deployment (no .env file there)". That assumption is false --
# .catalystignore is not reliably honoured by the deploy bundler (the same
# reason client/node_modules gets walked during an AppSail deploy), so a
# developer's local .env can ship inside the bundle. One carrying
# MOCK_NOSQL_ONLY=true silently switched the DEPLOYED backend onto an empty
# container-local mock store: every user lookup missed, so every login
# returned "Invalid username or password", and five of those tripped the
# lockout into a 429. Inside Catalyst the platform-injected environment
# variables are the only source of truth.
from dotenv import load_dotenv
if not os.getenv("X_ZOHO_CATALYST_LISTEN_PORT"):
    load_dotenv()

from backend.api.routes import query, health, transcribe, graph, tts, ocr, export, auth, exclusions, cases, sessions, feedback, hypothesis, translate, review_queue
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
        from shared.catalyst_client import (
            nosql_set, nosql_get, _mock_nosql_reason, _running_in_catalyst,
        )
        # BUG FIX: the old health check wrote a key then read the SAME key
        # back, which also succeeds against the local mock file -- so it
        # printed "passed" even when the app was silently using an empty
        # container-local store instead of real NoSQL (this is what made a
        # missing-config incident look like "Invalid username or password"
        # for every officer). Report which store is actually in use.
        reason = _mock_nosql_reason()
        if reason is None:
            print("[STARTUP] ✅ NoSQL target: real Catalyst AppKeyValueStore")
        else:
            where = "DEPLOYED" if _running_in_catalyst() else "local dev"
            print(f"[STARTUP] ⚠️  NoSQL target: LOCAL MOCK FILE ({where}) — reason: {reason}")

        await nosql_set("health:startup", "ok")
        result = await nosql_get("health:startup")
        print(f"[STARTUP] ✅ NoSQL health check passed: {result}")
    except Exception as e:
        print(f"[STARTUP] ❌ NoSQL health check FAILED — all queries will hang: {e}")

    # Check Signals URL — if missing, fallback inline runner is used which
    # may timeout long queries inside the AppSail event loop.
    signals_url = os.getenv("ZC_SIGNALS_PUBLISHER_URL") or os.getenv("CATALYST_SIGNALS_PUBLISHER_URL")
    if signals_url:
        print("[STARTUP] ✅ Signals URL is configured.")
    else:
        print("[STARTUP] ⚠️  ZC_SIGNALS_PUBLISHER_URL is NOT SET — pipeline will run inline (may timeout).")

    await init_nosql_client()
    yield
    await close_nosql_client()
    # BUG-05 FIX: close the Memgraph driver on app shutdown to release
    # the connection pool back to Memgraph instead of leaking it.
    from shared.graph_client import close as close_graph_driver
    await close_graph_driver()

# Disable public Swagger/Redoc API documentation for security.
# Exposing the API schema of a police intelligence system is an information disclosure vulnerability.
app = FastAPI(
    lifespan=lifespan,
    docs_url=None,
    redoc_url=None,
    openapi_url=None
)

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
app.include_router(hypothesis.router)
app.include_router(translate.router)
app.include_router(feedback.router)
app.include_router(review_queue.router)
