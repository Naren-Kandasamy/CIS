import httpx
import uuid
import hashlib
import os
import json
import asyncio

def _get_signals_url() -> str:
    return os.getenv("CATALYST_SIGNALS_PUBLISHER_URL")
QUERY_CACHE_TTL_SECONDS = 300  # short window

# Mocking NoSQL logic for week 1 skeleton
_nosql_mock_db = {}

async def nosql_get(key: str):
    return _nosql_mock_db.get(key)

async def nosql_set(key: str, value: str, ttl: int = None):
    _nosql_mock_db[key] = {"value": value}

async def read_job_status(job_id: str):
    doc = await nosql_get(f"job:{job_id}")
    if doc and "value" in doc:
        return json.loads(doc["value"])
    return None

async def write_job_status(job_id: str, session_id: str = None, query: str = None, status: str = None, result: dict = None, error: str = None):
    job = await read_job_status(job_id) or {}
    if session_id is not None: job["session_id"] = session_id
    if query is not None: job["query"] = query
    if status is not None: job["status"] = status
    if result is not None: job["result"] = result
    if error is not None: job["error"] = error
    await nosql_set(f"job:{job_id}", json.dumps(job))

def query_cache_key(query: str) -> str:
    normalized = query.strip().lower()
    digest = hashlib.sha256(normalized.encode()).hexdigest()[:16]
    return f"cache:full_query:{digest}"

async def dispatch_query_job(session_id: str, query: str) -> str:
    """
    Checks for a recent identical query first (full-pipeline short-circuit).
    If not cached, posts the job as an event to the Signals Custom Publisher
    and returns immediately -- does NOT wait for the pipeline, which runs
    separately as the Signals Function target.
    """
    cached = await nosql_get(query_cache_key(query))
    if cached:
        job_id = str(uuid.uuid4())
        cached_result = json.loads(cached["value"])
        await write_job_status(job_id, session_id, query, status="done", result=cached_result)
        return job_id

    job_id = str(uuid.uuid4())
    await write_job_status(job_id, session_id, query, status="queued")

    signals_url = _get_signals_url()
    if signals_url:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                signals_url,
                json={
                    "job_id": job_id,
                    "session_id": session_id,
                    "query": query,
                },
            )
            response.raise_for_status() 
    else:
        # LOCAL DEV: run pipeline as a background asyncio task in the same
        # process so it shares _nosql_mock_db with the SSE poller and can
        # write status updates that the poller will see.
        print(f"[Local Dev] Dispatching {job_id} inline via asyncio.create_task")
        asyncio.create_task(_local_pipeline_runner(job_id, session_id, query))

    return job_id

async def _local_pipeline_runner(job_id: str, session_id: str, query: str):
    """Local-dev-only pipeline runner. Replaced by Catalyst Signals in production."""
    from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline
    try:
        history_doc = await nosql_get(f"history:{session_id}")
        history = json.loads(history_doc["value"]) if history_doc else []
        
        await run_langgraph_pipeline(job_id, query, write_job_status, history)
        
        # After completion, append to history and save
        job = await read_job_status(job_id)
        if job and job.get("status") == "done":
            history.append({"q": query, "a": job["result"]["answer"]})
            history = history[-10:] # Cap history to 10
            await nosql_set(f"history:{session_id}", json.dumps(history))
            
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"[Local pipeline error] {e}")
        await write_job_status(job_id, status="failed", error=str(e))
