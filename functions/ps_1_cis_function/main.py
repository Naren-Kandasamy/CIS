import logging
import json
import asyncio
import sys
import os
import traceback

# DEPLOY FIX: shared/ and pipeline_function/ are physically copied into this
# function folder at deploy time. job_dispatch is a local shim using shared/
# only — no dependency on the backend AppSail package.

from job_dispatch import write_job_status, read_job_status, nosql_get, nosql_set
from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline
from shared.graph_client import run_query
from shared.catalyst_client import get_session_lock

# ── Diagnostic: log which env vars are present at import time ──────────────
_REQUIRED_VARS = [
    "ZC_REFRESH_TOKEN", "ZC_CLIENT_ID", "ZC_CLIENT_SECRET",
    "MEMGRAPH_URI", "MEMGRAPH_USERNAME",
    "ZC_LLM_API_KEY",
]
print("[DIAG][IMPORT] ps_1_cis_function starting up")
for _v in _REQUIRED_VARS:
    _val = os.getenv(_v)
    print(f"[DIAG][ENV]  {_v} = {'SET (' + str(len(_val)) + ' chars)' if _val else 'NOT SET ⚠️'}")

logger = logging.getLogger()

async def warm_connections():
    """
    Run once per cold start, before handling events.
    """
    try:
        await run_query("RETURN 1 as warmup")
    except Exception as e:
        print(f"Warm-up failed: {e}")

# BUG FIX: warm_connections() was previously defined but never called, so the
# Memgraph connection was never pre-warmed on cold start. Called here, matching
# pipeline_function/main.py.
_warmed_up = False

def handler(event, context):
    """
    Triggered as a Signals Function target. Runs the full LangGraph pipeline.
    """
    global _warmed_up
    print("[DIAG][HANDLER] handler() called")

    # ── Step 1: Parse the incoming event ──────────────────────────────────
    try:
        raw_data = event.get_raw_data()
        print(f"[DIAG][HANDLER] raw_data keys: {list(raw_data.keys()) if isinstance(raw_data, dict) else type(raw_data)}")
        raw_event_data = raw_data['events'][0]['data']
        print(f"[DIAG][HANDLER] raw_event_data type: {type(raw_event_data)}")

        # CRITICAL FIX: job_dispatch.py sends data as json.dumps({...}) — a
        # JSON string, not a dict. Must parse it here before subscripting.
        if isinstance(raw_event_data, str):
            job_data = json.loads(raw_event_data)
        else:
            job_data = raw_event_data  # already parsed by SDK

        # Catalyst sometimes wraps the entire POST JSON payload in another 'data' key
        if "data" in job_data and isinstance(job_data["data"], str):
            job_data = json.loads(job_data["data"])
        elif "data" in job_data and isinstance(job_data["data"], dict):
            job_data = job_data["data"]
            
        print(f"[DIAG][HANDLER] Final job_data keys: {list(job_data.keys())}")

        job_id = job_data["job_id"]
        session_id = job_data["session_id"]
        query = job_data["query"]
        print(f"[DIAG][HANDLER] ✅ Parsed job_id={job_id} session={session_id} query={query[:60]!r}")
    except Exception as e:
        print(f"[DIAG][HANDLER] ❌ Event parsing failed: {e}")
        traceback.print_exc()
        context.close_with_failure()
        return

    # ── Step 2: Warm up connections on cold start ──────────────────────────
    if not _warmed_up:
        print("[DIAG][HANDLER] Cold start — warming up Memgraph connection...")
        try:
            asyncio.run(warm_connections())
            print("[DIAG][HANDLER] ✅ Warm-up complete")
        except Exception as e:
            print(f"[DIAG][HANDLER] ⚠️ Warm-up failed (non-fatal): {e}")
        _warmed_up = True

    # ── Step 3: Run pipeline ───────────────────────────────────────────────
    print(f"[DIAG][HANDLER] Starting pipeline for job {job_id}")
    try:
        asyncio.run(_run_pipeline(job_id, session_id, query))
        print(f"[DIAG][HANDLER] ✅ Pipeline complete for job {job_id}")
        context.close_with_success()
    except Exception as e:
        print(f"[DIAG][HANDLER] ❌ Pipeline crashed: {e}")
        traceback.print_exc()
        context.close_with_failure()

async def _run_pipeline(job_id: str, session_id: str, query: str):
    print(f"[DIAG][PIPELINE] _run_pipeline started for job {job_id}")

    # ── Idempotency check ──────────────────────────────────────────────────
    print(f"[DIAG][PIPELINE] Reading existing job status from NoSQL...")
    try:
        existing = await read_job_status(job_id)
        print(f"[DIAG][PIPELINE] Existing status: {existing.get('status') if existing else 'None'}")
    except Exception as e:
        print(f"[DIAG][PIPELINE] ❌ NoSQL read failed: {e}")
        traceback.print_exc()
        raise

    if existing and existing.get("status") != "queued":
        print(f"[DIAG][PIPELINE] Skipping duplicate — status is '{existing.get('status')}'")
        return

    try:
        # ── Read session history ───────────────────────────────────────────
        print(f"[DIAG][PIPELINE] Acquiring session lock for history read...")
        async with get_session_lock(session_id):
            history_doc = await nosql_get(f"history:{session_id}")
            history = json.loads(history_doc["value"]) if history_doc else []
        print(f"[DIAG][PIPELINE] History loaded: {len(history)} entries")

        # ── Run LangGraph pipeline ─────────────────────────────────────────
        print(f"[DIAG][PIPELINE] Invoking run_langgraph_pipeline...")
        await run_langgraph_pipeline(job_id, query, write_job_status, history)
        print(f"[DIAG][PIPELINE] ✅ run_langgraph_pipeline returned")

        # ── Write updated history ──────────────────────────────────────────
        print(f"[DIAG][PIPELINE] Writing updated history...")
        async with get_session_lock(session_id):
            job = await read_job_status(job_id)
            if job and job.get("status") == "done":
                history_doc = await nosql_get(f"history:{session_id}")
                history = json.loads(history_doc["value"]) if history_doc else []
                history.append({"q": query, "a": job["result"]["answer"]})
                history = history[-10:]
                await nosql_set(f"history:{session_id}", json.dumps(history))
                print(f"[DIAG][PIPELINE] ✅ History updated ({len(history)} entries)")

    except Exception as e:
        print(f"[DIAG][PIPELINE] ❌ Pipeline failed at step: {e}")
        traceback.print_exc()
        # BUG FIX (info leak): error=str(e) put the raw exception text straight
        # into the job's client-facing error field, which sse_poller.py streams
        # directly to the browser over SSE -- leaking internal details (file
        # paths, driver/host info, stack message shapes) to whichever officer's
        # query happened to hit this outer handler. This is the primary
        # Signals-dispatched pipeline path (backend/job_dispatch.py's inline
        # runner is the local-dev-only fallback, already fixed with the same
        # pattern) -- the real exception is already logged server-side via
        # traceback.print_exc() and the print() above; only a generic message
        # goes to the client now.
        try:
            await write_job_status(job_id, status="failed", error="Pipeline processing failed, please retry.")
        except Exception as write_error:
            print(f"[DIAG][PIPELINE] ❌ Also failed to write failed status: {write_error}")
        raise  # re-raise so handler can call close_with_failure()
