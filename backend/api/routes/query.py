from fastapi import APIRouter, HTTPException, Request
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, field_validator
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
    query: str = Field(..., min_length=1, max_length=500)

    # BUG FIX (IDOR, keyspace collision): this route's session_id has no
    # format restriction and shares its NoSQL key prefixes (session_owner:,
    # history:) with backend/api/routes/cases.py's case-scoped sessions
    # (id format "s_" + secrets.token_hex(4)), which are gated by a real
    # collaborator ACL (see sessions.py's get_session_history). /api/query's
    # own ownership check is first-claim-wins with no case ACL at all -- an
    # attacker who managed to submit a session_id matching a real case
    # session's "s_..." id would piggyback onto (and later read back) that
    # case's history, bypassing the collaborator check entirely. Not
    # exploitable today (the frontend never feeds a case-scoped session_id
    # into /api/query, and the id space is only 32 bits, infeasible to guess
    # under the rate limit below) -- this rejects the reserved prefix
    # outright so the two id spaces can never collide, now or after the
    # case/session-integration cutover noted in cases.py's scope note.
    @field_validator("session_id")
    @classmethod
    def reject_case_scoped_prefix(cls, v):
        if v.startswith("s_"):
            raise ValueError("session_id must not use the reserved case-session prefix")
        return v

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
    # server-side ownership check at all -- any authenticated officer
    # submitting any other officer's session_id got that session's stored
    # conversation history used as LLM context and appended to (see
    # backend/job_dispatch.py's history:{session_id} read/write). A full
    # case/session-ownership model already exists (backend/api/routes/cases.py)
    # but wiring /api/query to require a case-registered session_id is a
    # breaking change to the client's current UUID-per-tab contract that has
    # to land together with frontend rewiring (tracked separately, not done
    # here). This is the safe, non-breaking version: the first officer to use
    # a given session_id claims it; any other officer trying to reuse that
    # same session_id is rejected. No TTL, matching history:{session_id}
    # itself (job_dispatch.py never sets one either).
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
    job_id = await dispatch_query_job(request.session_id, request.query)
    return EventSourceResponse(stream_job_status(job_id))
