import httpx
import uuid
import hashlib
import os
import json
import asyncio

# BUG FIX: this used to define its own separate in-memory mock
# (_nosql_mock_db), entirely disconnected from shared/catalyst_client.py's
# own separate mock. Neither was ever wired to a real Catalyst NoSQL table --
# job status written by the pipeline Function (a different deployed process)
# could never be seen by this AppSail process reading it back for the SSE
# poller. Now both use the same real NoSQL-backed functions.
from shared.catalyst_client import nosql_get, nosql_set, get_session_lock

def _get_signals_url() -> str:
    # BUG FIX: Catalyst AppSail rejects any deployed env var key containing
    # "CATALYST" as reserved, so this is set as ZC_SIGNALS_PUBLISHER_URL in
    # production; CATALYST_SIGNALS_PUBLISHER_URL is kept as a local-dev alias.
    return os.getenv("ZC_SIGNALS_PUBLISHER_URL") or os.getenv("CATALYST_SIGNALS_PUBLISHER_URL")
QUERY_CACHE_TTL_SECONDS = 300  # short window

# BUG FIX: asyncio.create_task()'s returned Task was previously discarded with
# no reference kept, making it eligible for GC mid-execution (a documented
# asyncio pitfall) -- silently dropping an in-flight query. Retained here.
_background_tasks: set = set()

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
    dispatched_via_signals = False
    
    if signals_url:  # Use Catalyst Signals when URL is configured
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                print(f"[Signals] POSTing job {job_id} to Signals URL...")
                response = await client.post(
                    signals_url,
                    json={
                        "data": json.dumps({
                            "job_id": job_id,
                            "session_id": session_id,
                            "query": query,
                        })
                    },
                )
                response.raise_for_status()
                print(f"[Signals] ✅ Dispatch succeeded — HTTP {response.status_code} for job {job_id}")
                dispatched_via_signals = True
            except Exception as e:
                print(f"[Signals] ❌ Dispatch FAILED for job {job_id}: {type(e).__name__}: {e} — falling back to inline runner")
                dispatched_via_signals = False
    else:
        print(f"[Signals] ⚠️  ZC_SIGNALS_PUBLISHER_URL not set — running inline fallback for job {job_id}")

    if not dispatched_via_signals:
        # LOCAL DEV or Fallback: run pipeline as a background asyncio task in the same
        # process as the SSE poller, so both see the same real NoSQL-backed
        # job status via shared.catalyst_client.
        print(f"[Fallback/Local Dev] Dispatching {job_id} inline via asyncio.create_task")
        task = asyncio.create_task(_local_pipeline_runner(job_id, session_id, query))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return job_id

async def _local_pipeline_runner(job_id: str, session_id: str, query: str):
    """Local-dev-only pipeline runner. Replaced by Catalyst Signals in production."""
    from pipeline_function.pipeline.langgraph_router import run_langgraph_pipeline
    try:
        # RC-02 FIX: previously held the session lock for the ENTIRE pipeline
        # duration (30-60s including LLM calls), which completely blocked any
        # second query in the same session until the first finished. The lock
        # only needs to guard the history read-modify-write, not the pipeline
        # execution itself. Split into two narrow critical sections instead.

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
        import traceback
        traceback.print_exc()
        print(f"[Local pipeline error] {e}")
        # BUG FIX (info leak): error=str(e) put the raw exception text
        # straight into the job's client-facing error field, which
        # sse_poller.py streams directly to the browser over SSE --
        # leaking internal details (file paths, driver/host info, stack
        # message shapes) to whichever officer's query happened to hit this
        # outer handler (session-lock/history code around the pipeline call,
        # not run_langgraph_pipeline's own already-sanitized error path). The
        # real exception is already logged server-side via traceback.print_exc()
        # and the print() above; only a generic message goes to the client now.
        #
        # BUG FIX: this failure-reporting call can itself hit the same
        # transient NoSQL connectivity issue that caused the original
        # failure -- previously unguarded, so a double-failure crashed the
        # whole background task as an unretrieved exception instead of just
        # logging that the job's failure status couldn't be persisted.
        try:
            await write_job_status(job_id, status="failed", error="Pipeline processing failed, please retry.")
        except Exception as write_error:
            print(f"[Local pipeline error] Also failed to write failed status: {write_error}")

