from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel

from backend.sse_poller import stream_job_status

router = APIRouter()

class QueryRequest(BaseModel):
    session_id: str
    query: str

@router.post("/api/query")
async def query(request: QueryRequest):
    from backend.job_dispatch import dispatch_query_job
    job_id = await dispatch_query_job(request.session_id, request.query)
    return EventSourceResponse(stream_job_status(job_id))
