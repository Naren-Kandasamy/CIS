from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from pydantic import BaseModel, Field, field_validator
import re

from backend.sse_poller import stream_job_status

router = APIRouter()

UUID4_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$', re.I
)

class QueryRequest(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=64)
    query: str = Field(..., min_length=1, max_length=500)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, v: str) -> str:
        if not UUID4_PATTERN.match(v):
            raise ValueError("session_id must be a valid UUID v4")
        return v

from backend.job_dispatch import dispatch_query_job

@router.post("/api/query")
async def query(request: QueryRequest):
    job_id = await dispatch_query_job(request.session_id, request.query)
    return EventSourceResponse(stream_job_status(job_id))
