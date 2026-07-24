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

def handler(event, context):
    """
    Triggered as a Signals Function target -- invoked when the Rule routes an
    event from the Custom Publisher here. Runs the full LangGraph pipeline
    inside this single invocation.
    """
    global _warmed_up
    if not _warmed_up:
        try:
            asyncio.run(warm_connections())
        except Exception as e:
            print(f"Warm-up failed (non-fatal): {e}")
        _warmed_up = True
    raw_data = event.get_raw_data()
    job_data = raw_data['events'][0]['data']

    job_id = job_data["job_id"]
    session_id = job_data["session_id"]
    query = job_data["query"]
    logger.info(f"Received job {job_id} for session {session_id}")

    asyncio.run(_run_pipeline(job_id, session_id, query))
    context.close_with_success()

async def _run_pipeline(job_id: str, session_id: str, query: str):
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

        # Run the pipeline WITHOUT holding the session lock
        await run_langgraph_pipeline(job_id, query, write_job_status, history, session_id=session_id)

        # --- Narrow lock: write updated history after pipeline ---
        async with get_session_lock(session_id):
            job = await read_job_status(job_id)
            if job and job.get("status") == "done":
                # Re-read history inside the lock to catch concurrent updates
                history_doc = await nosql_get(f"history:{session_id}")
                history = json.loads(history_doc["value"]) if history_doc else []
                history.append({"q": query, "a": job["result"]["answer"]})
                history = history[-10:]  # Cap history to 10
                await nosql_set(f"history:{session_id}", json.dumps(history))

    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        # BUG FIX: guard against this failure-reporting call itself hitting
        # the same transient NoSQL connectivity issue that caused the
        # original failure -- otherwise a double-failure crashes the whole
        # invocation as an unretrieved exception instead of just logging it.
        try:
            await write_job_status(job_id, status="failed", error=str(e))
        except Exception as write_error:
            logger.error(f"Also failed to write failed status: {write_error}")


