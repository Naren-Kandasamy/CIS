import logging
import json
import asyncio

logger = logging.getLogger()

def handler(event, context):
    """
    Triggered as a Signals Function target -- invoked when the Rule routes an
    event from the Custom Publisher here. Runs the full LangGraph pipeline
    inside this single invocation.
    """
    raw_data = event.get_raw_data()
    job_data = raw_data['events'][0]['data']

    job_id = job_data["job_id"]
    session_id = job_data["session_id"]
    query = job_data["query"]
    logger.info(f"Received job {job_id} for session {session_id}")

    asyncio.run(_run_pipeline(job_id, session_id, query))
    context.close_with_success()

async def _run_pipeline(job_id: str, session_id: str, query: str):
    import sys
    import os
    # Add root project directory to path so imports work correctly inside Catalyst container
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
    
    from backend.job_dispatch import write_job_status
    from pipeline_function.pipeline.template_router import run_template_router
    
    try:
        await run_template_router(job_id, query, write_job_status)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        await write_job_status(job_id, status="failed", error=str(e))

async def warm_connections():
    """
    Run once per cold start, before handling events.
    """
    try:
        from shared.graph_client import run_query
        await run_query("RETURN 1 as warmup")
    except Exception as e:
        print(f"Warm-up failed: {e}")
