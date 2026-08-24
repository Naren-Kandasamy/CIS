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

async def _main_async(job_id: str, session_id: str, query: str, language: str):
    global _warmed_up
    if not _warmed_up:
        print("[DIAG][HANDLER] Cold start — warming up Memgraph connection...")
        try:
            await warm_connections()
            print("[DIAG][HANDLER] ✅ Warm-up complete")
        except Exception as e:
            print(f"[DIAG][HANDLER] ⚠️ Warm-up failed (non-fatal): {e}")
        _warmed_up = True

    print(f"[DIAG][HANDLER] Starting pipeline for job {job_id}")
    await _run_pipeline(job_id, session_id, query, language)
    print(f"[DIAG][HANDLER] ✅ Pipeline complete for job {job_id}")

_loop = None

def handler(event, context):
    """
    Triggered as a Signals Function target. Runs the full LangGraph pipeline.
    """
    global _warmed_up, _loop
    print("[DIAG][HANDLER] handler() called")

    # CRITICAL WORKAROUND: langchain_core caches a global ThreadPoolExecutor.
    # In a serverless environment, background threads may be killed or atexit 
    # hooks run between invocations, leaving this executor in a "shutdown" state.
    # BUG FIX: simply clearing the cache leaked the old threads, leading to an OOM SIGKILL.
    try:
        import langchain_core.callbacks.manager
        if hasattr(langchain_core.callbacks.manager._executor, "cache_info"):
            if langchain_core.callbacks.manager._executor.cache_info().currsize > 0:
                executor = langchain_core.callbacks.manager._executor()
                if hasattr(executor, "shutdown"):
                    executor.shutdown(wait=False)
        langchain_core.callbacks.manager._executor.cache_clear()
    except Exception as e:
        print(f"[DIAG][HANDLER] ⚠️ Failed to clear langchain_core executor cache: {e}")

    # BUG FIX: anyio (used by httpx) caches its ThreadPoolExecutor globally.
    # Using `asyncio.run()` creates a new loop per invocation, but when it exits,
    # it shuts down the executor. Subsequent invocations will try to use the 
    # shut down executor and crash with "cannot schedule new futures after shutdown".
    # We use a persistent global event loop to keep the executor alive.
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

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

        # Warm-up ping
        if job_data.get("warmup"):
            print("[DIAG][HANDLER] Warm-up ping received")
            if not _warmed_up:
                try:
                    _loop.run_until_complete(warm_connections())
                    _warmed_up = True
                    print("[DIAG][HANDLER] ✅ Warm-up complete")
                except Exception as e:
                    print(f"[DIAG][HANDLER] ⚠️ Warm-up failed (non-fatal): {e}")
            context.close_with_success()
            return

        job_id = job_data["job_id"]
        session_id = job_data["session_id"]
        query = job_data["query"]
        language = job_data.get("language", "en")
        print(f"[DIAG][HANDLER] ✅ Parsed job_id={job_id} session={session_id} query={query[:60]!r} language={language}")
    except Exception as e:
        print(f"[DIAG][HANDLER] ❌ Event parsing failed: {e}")
        traceback.print_exc()
        context.close_with_failure()
        return

    # ── Step 2 & 3: Warm up and Run pipeline ───────────────────────────────
    try:
        _loop.run_until_complete(_main_async(job_id, session_id, query, language))
        context.close_with_success()
    except Exception as e:
        print(f"[DIAG][HANDLER] ❌ Pipeline crashed: {e}")
        traceback.print_exc()
        context.close_with_failure()

async def _run_pipeline(job_id: str, session_id: str, query: str, language: str = "en"):
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

            session_doc = await nosql_get(f"session:{session_id}")
            session_state = json.loads(session_doc["value"]) if session_doc else {}
        print(f"[DIAG][PIPELINE] History loaded: {len(history)} entries")

        # ── Run LangGraph pipeline ─────────────────────────────────────────
        print(f"[DIAG][PIPELINE] Invoking run_langgraph_pipeline...")
        result_data = await run_langgraph_pipeline(job_id, query, write_job_status, history, session_state=session_state, session_id=session_id, language=language)
        print(f"[DIAG][PIPELINE] ✅ run_langgraph_pipeline returned")

        # ── Write updated history ──────────────────────────────────────────
        print(f"[DIAG][PIPELINE] Writing updated history...")
        async with get_session_lock(session_id):
            if result_data:
                history_doc = await nosql_get(f"history:{session_id}")
                history = json.loads(history_doc["value"]) if history_doc else []
                history.append({"q": query, "a": result_data.get("answer", "")})
                history = history[-10:]
                await nosql_set(f"history:{session_id}", json.dumps(history))
                print(f"[DIAG][PIPELINE] ✅ History updated ({len(history)} entries)")

                intent = result_data.get("intent_parsed", {}).get("intent")
                if intent not in ["malicious", "greeting", "fallback"]:
                    new_session_state = {
                        "prior_query": query,
                        "prior_entity_json": result_data.get("intent_parsed", {}).get("entities", {}),
                        "prior_evidence_items": result_data.get("evidence", [])
                    }
                    await nosql_set(f"session:{session_id}", json.dumps(new_session_state))

    except Exception as e:
        print(f"[DIAG][PIPELINE] ❌ Pipeline failed at step: {e}")
        traceback.print_exc()
        try:
            await write_job_status(job_id, status="failed", error="Pipeline processing failed, please retry.")
        except Exception as write_error:
            print(f"[DIAG][PIPELINE] ❌ Also failed to write failed status: {write_error}")
        raise  # re-raise so handler can call close_with_failure()
