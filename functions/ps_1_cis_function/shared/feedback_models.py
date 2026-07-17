from pydantic import BaseModel, Field
from typing import Optional

# BUG FIX: none of these string fields had a max_length, so an authenticated
# officer could POST arbitrarily large query_text/explanation/etc. on every
# /api/feedback/correction call, each of which gets persisted verbatim as a
# correction:{event_id} NoSQL record with no size cap -- unbounded storage
# growth. Bounds below are generous but finite. Note: the rest of that audit
# finding (capping the session_penalty set in _apply_session_penalty, adding a
# TTL to correction:{event_id}/trust:{scope_key} writes, and catching
# httpx.HTTPStatusError in _nosql_request) lives in feedback_engine.py and
# catalyst_client.py, outside this file's scope -- not addressed here.
class CorrectionEvent(BaseModel):
    event_id: str = Field(max_length=64)
    session_id: str = Field(max_length=128)
    officer_id: str = Field(max_length=128)
    timestamp: str = Field(max_length=64)
    query_text: str = Field(max_length=2000)
    edge_type: str = Field(max_length=128)
    crime_type: Optional[str] = Field(default=None, max_length=128)
    edge_id: Optional[str] = Field(default=None, max_length=128)
    verdict: str = Field(max_length=32)                       # "confirmed" | "corrected"
    explanation: Optional[str] = Field(default=None, max_length=4000)  # captured verbatim, never auto-parsed

class MethodologyTrust(BaseModel):
    scope_key: str
    confirmations: int = 0
    corrections: int = 0
