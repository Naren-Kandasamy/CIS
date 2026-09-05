import logging
import json
import asyncio
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from backend.job_dispatch import write_job_status, read_job_status, nosql_get, nosql_set
from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline
from shared.graph_client import run_query
from shared.catalyst_client import get_session_lock

logger = logging.getLogger()

async def warm_connections():
    """
    Run once per cold start, before handling events.
    """
    try:
        await run_query("RETURN 1 as warmup")
    except Exception as e:
        print(f"Warm-up failed: {e}")

_warmed_up = False

async def _main_async(job_id: str, session_id: str, query: str, language: str):
    global _warmed_up
    if not _warmed_up:
        try:
            await warm_connections()
        except Exception as e:
            print(f"Warm-up failed (non-fatal): {e}")
        _warmed_up = True

    await _run_pipeline(job_id, session_id, query, language)

_loop = None

def handler(event, context):
    """
    Triggered as a Signals Function target -- invoked when the Rule routes an
    event from the Custom Publisher here. Runs the full LangGraph pipeline
    inside this single invocation.
    """
    global _warmed_up, _loop
    raw_data = event.get_raw_data()
    
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
        logger.warning(f"Failed to clear langchain_core executor cache: {e}")

    # BUG FIX: anyio (used by httpx) caches its ThreadPoolExecutor globally.
    # Using `asyncio.run()` creates a new loop per invocation, but when it exits,
    # it shuts down the executor. Subsequent invocations will try to use the 
    # shut down executor and crash with "cannot schedule new futures after shutdown".
    # We use a persistent global event loop to keep the executor alive.
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)

    try:
        job_data = raw_data['events'][0]['data']
        
        # Catalyst sometimes wraps the entire POST JSON payload in another 'data' key
        if isinstance(job_data, str):
            job_data = json.loads(job_data)
        if "data" in job_data and isinstance(job_data["data"], str):
            job_data = json.loads(job_data["data"])
        elif "data" in job_data and isinstance(job_data["data"], dict):
            job_data = job_data["data"]

        # Warm-up ping
        if job_data.get("warmup"):
            logger.info("Warm-up ping received")
            if not _warmed_up:
                try:
                    _loop.run_until_complete(warm_connections())
                    _warmed_up = True
                    logger.info("Warm-up complete")
                except Exception as e:
                    logger.error(f"Warm-up failed (non-fatal): {e}")
            context.close_with_success()
            return

        job_id = job_data["job_id"]
        session_id = job_data["session_id"]
        query = job_data["query"]
        language = job_data.get("language", "en")
        logger.info(f"Received job {job_id} for session {session_id} (language: {language})")

        _loop.run_until_complete(_main_async(job_id, session_id, query, language))
        context.close_with_success()
    except Exception as e:
        logger.error(f"Pipeline crashed: {e}")
        context.close_with_failure()

async def _run_pipeline(job_id: str, session_id: str, query: str, language: str = "en"):
    # BUG FIX: no idempotency guard previously existed -- a redelivered
    # Signals event (at-least-once delivery) for the same job_id would run
    # the entire pipeline twice, double-spending LLM calls and double-writing
    # history. A job only sits at "queued" until the first real pipeline node
    # runs (understanding_query_node writes status immediately), so a
    # redelivery arriving after that sees a non-"queued" status and skips.
    existing = await read_job_status(job_id)
    if existing and existing.get("status") != "queued":
        logger.info(f"Job {job_id} already in progress/done (status={existing.get('status')}) -- skipping duplicate invocation")
        return

    try:
        # --- Narrow lock: read history snapshot before pipeline ---
        async with get_session_lock(session_id):
            history_doc = await nosql_get(f"history:{session_id}")
            history = json.loads(history_doc["value"]) if history_doc else []
            
            session_doc = await nosql_get(f"session:{session_id}")
            session_state = json.loads(session_doc["value"]) if session_doc else {}

        # Run the pipeline WITHOUT holding the session lock
        result_data = await run_langgraph_pipeline(job_id, query, write_job_status, history, session_state=session_state, session_id=session_id, language=language)

        # --- Narrow lock: write updated history after pipeline ---
        async with get_session_lock(session_id):
            if result_data:
                # Re-read history inside the lock to catch concurrent updates
                history_doc = await nosql_get(f"history:{session_id}")
                history = json.loads(history_doc["value"]) if history_doc else []
                # Persist evidence + visualization alongside {q, a} so
                # GET /api/sessions/{sid} restores the FULL turn on reload --
                # the evidence cards and the graph/map, not just the text.
                # Evidence items carry a whole FIR record in .data; cap the
                # count per turn so a 10-turn history doc stays inside the
                # NoSQL value-size limit.
                history.append({
                    "q": query,
                    "a": result_data.get("answer", ""),
                    "evidence": (result_data.get("evidence") or [])[:40],
                    "visualization": result_data.get("visualization") or {},
                })
                history = history[-10:]  # Cap history to 10
                await nosql_set(f"history:{session_id}", json.dumps(history))
                
                # Write back the session state for coreference and follow-up
                # GUARD: only overwrite valid investigative state if the new query wasn't a firewall block/fallback
                intent = result_data.get("intent_parsed", {}).get("intent")
                if intent not in ["malicious", "greeting", "fallback"]:
                    new_session_state = {
                        "prior_query": query,
                        "prior_entity_json": result_data.get("intent_parsed", {}).get("entities", {}),
                        "prior_evidence_items": result_data.get("evidence", [])
                    }
                    await nosql_set(f"session:{session_id}", json.dumps(new_session_state))

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        # BUG FIX (info leak): error=str(e) put the raw exception text straight
        # into the job's client-facing error field, which sse_poller.py streams
        # directly to the browser over SSE. The real exception is already
        # logged server-side via logger.error() above; only a generic message
        # goes to the client now.
        #
        # BUG FIX: guard against this failure-reporting call itself hitting
        # the same transient NoSQL connectivity issue that caused the
        # original failure -- otherwise a double-failure crashes the whole
        # invocation as an unretrieved exception instead of just logging it.
        try:
            await write_job_status(job_id, status="failed", error="Pipeline processing failed, please retry.")
        except Exception as write_error:
            logger.error(f"Also failed to write failed status: {write_error}")


