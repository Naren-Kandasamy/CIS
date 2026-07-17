from pydantic import BaseModel
from typing import Optional

class CorrectionEvent(BaseModel):
    event_id: str
    session_id: str
    officer_id: str
    timestamp: str
    query_text: str
    edge_type: str
    crime_type: Optional[str] = None
    edge_id: Optional[str] = None
    verdict: str                       # "confirmed" | "corrected"
    explanation: Optional[str] = None  # captured verbatim, never auto-parsed

class MethodologyTrust(BaseModel):
    scope_key: str
    confirmations: int = 0
    corrections: int = 0
