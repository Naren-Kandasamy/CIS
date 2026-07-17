from pydantic import BaseModel
from typing import Optional
import uuid
from datetime import datetime

class ClaimRecord(BaseModel):
    claim_id: str
    fir_id: str
    accused_id: Optional[str] = None
    evidence_ref: Optional[str] = None
    confidence_tier: str          # "HIGH" | "MEDIUM" | "LOW"
    synthesized_snippet: str      # short excerpt of what was claimed, for the alert
    timestamp: str
    contradicted: bool = False
    contradicted_date: Optional[str] = None
