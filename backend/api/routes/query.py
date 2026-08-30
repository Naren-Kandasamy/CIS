from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field
import re

from backend.sse_poller import stream_job_status
from shared.catalyst_client import nosql_get, nosql_set, get_lock

router = APIRouter()

UUID4_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.I
)

# BUG FIX: no per-officer rate limit existed on this route at all -- any
# authenticated officer could script an unbounded loop of queries, each
# triggering a full pipeline dispatch (NER/DAG/retrieval/LLM synthesis).
QUERY_RATE_LIMIT = 30
QUERY_RATE_WINDOW_SECONDS = 60

class QueryRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=2000)
    language: str = Field(default="en", max_length=16)

    # The IDOR and keyspace collision fixes have been upgraded to fully support
    # case-scoped sessions ("s_..." prefix). The explicit block on this prefix
    # is removed, and authorization now delegates to the case's collaborator ACL
    # for these sessions, while retaining the first-claim-wins lock for legacy
    # UUID tab sessions.

    # BUG FIX: this field_validator's denylist (bare \b(match|create|delete|
    # drop|insert|update|alter|truncate|merge|set|remove)\b) matched those
    # words ANYWHERE in the query, including ordinary English ("Do any cases
    # match this MO?", "Can you update me on the status?") -- rejecting
    # legitimate officer queries with a 422, while providing negligible real
    # injection protection (the actual Cypher/SQL builders downstream
    # parameterize every value; this never reached them). The real,
    # correctly-scoped protection already runs on this exact path at the ASGI
    # layer: InputValidationMiddleware (backend/api/middleware/input_validator.py)
    # matches real SQL/Cypher syntax shapes (e.g. `MATCH\s*\(`, `UPDATE\s+.*?\s+SET`,
    # not bare keywords) for any POST whose path ends in "/query", which
    # /api/query always is. Removing this redundant, broken duplicate does not
    # reduce protection -- it removes a check that was net-negative (blocking
    # legitimate input) while the real check keeps running unchanged.

from backend.job_dispatch import dispatch_query_job

async def _authorize_session(session_id: str, username: str):
    # BUG FIX (IDOR): session_id is a client-generated UUID4 with no
    # server-side ownership check at all. We now support two session types:
    # 1. Case-scoped sessions (s_...) which use the case's collaborator ACL.
    # 2. Legacy UUID sessions which use first-claim-wins ownership.
    if session_id.startswith("s_"):
        import json
        from backend.api.routes.cases import _require_collaborator
        meta_doc = await nosql_get(f"session_meta:{session_id}")
        if not meta_doc:
            raise HTTPException(404, "Session not found")
        meta = json.loads(meta_doc["value"])
        await _require_collaborator(meta["case_id"], username)
        return

    key = f"session_owner:{session_id}"
    async with get_lock(key):
        doc = await nosql_get(key)
        if doc is None:
            await nosql_set(key, username)
            return
        if doc["value"] != username:
            raise HTTPException(403, "This session belongs to a different officer")

async def _enforce_query_rate_limit(username: str):
    key = f"query_rate:{username}"
    async with get_lock(key):
        existing = await nosql_get(key)
        count = int(existing["value"]) if existing else 0
        if count >= QUERY_RATE_LIMIT:
            raise HTTPException(
                429,
                f"Query rate limit exceeded -- max {QUERY_RATE_LIMIT} queries per {QUERY_RATE_WINDOW_SECONDS}s"
            )
        await nosql_set(key, str(count + 1), ttl=QUERY_RATE_WINDOW_SECONDS)

@router.post("/api/query")
async def query(request: QueryRequest, http_request: Request):
    username = getattr(http_request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    await _enforce_query_rate_limit(username)
    await _authorize_session(request.session_id, username)
    job_id = await dispatch_query_job(request.session_id, request.query, request.language)
    return EventSourceResponse(stream_job_status(job_id))


# Pre-warms the pipeline Function. Deliberately does no work of its own and
# returns immediately -- the client calls this in the background so the first
# real query doesn't pay the container's cold-start cost. Kept behind auth so
# it cannot be used as an unauthenticated way to spin up the Function.
@router.post("/api/warmup")
async def warmup(http_request: Request):
    username = getattr(http_request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")
    from backend.job_dispatch import dispatch_warmup
    dispatched = await dispatch_warmup()
    return {"status": "ok", "dispatched": dispatched}


# BUG FIX: there was no way to retrieve a job's result once its SSE stream had
# ended. AppSail closes the response after ~45s, but a cold Function start plus
# a slow synthesis can take longer -- the pipeline finishes and writes its
# answer to NoSQL, yet the client is left on the last progress stage with no
# terminal event and no means of recovery. This lets the client fetch a
# completed job after a dropped stream.
@router.get("/api/query/status/{job_id}")
async def query_status(job_id: str, http_request: Request):
    username = getattr(http_request.state, "username", None)
    if not username:
        raise HTTPException(401, "No authenticated session")

    from backend.job_dispatch import read_job_status
    job = await read_job_status(job_id)
    if not job:
        raise HTTPException(404, "Unknown job")

    status = job.get("status")
    if status == "failed":
        return {"status": "failed", "error": "Pipeline processing failed, please retry."}
    if status != "done":
        return {"status": status or "queued"}

    result = job.get("result") or {}
    return {
        "status": "done",
        "answer": result.get("answer", ""),
        "evidence": result.get("evidence", []),
        "visualization": result.get("visualization"),
    }
