# PS-1 Phase 5, item 1: Negative Evidence & Exclusion Tracking.
# See Docs/PS1_Negative_Evidence_Exclusion_Tracking.md Section 4.1.

from pydantic import BaseModel
from typing import Optional


class ExclusionRecord(BaseModel):
    exclusion_id: str
    fir_id: str
    accused_id: str
    exclusion_type: str                      # "ruled_out" | "alibi_confirmed"
    reason: str
    time_window_start: Optional[str] = None  # ISO datetime, alibi_confirmed only
    time_window_end: Optional[str] = None
    verification_method: Optional[str] = None
    officer_id: str
    date: str
    status: str = "active"                   # "active" | "reversed"
    reversed_by: Optional[str] = None
    reversed_reason: Optional[str] = None
    reversed_date: Optional[str] = None


class ContradictionRecord(BaseModel):
    contradiction_id: str
    evidence_ref: str
    fir_id: str
    reason: str
    contradicting_evidence_ref: Optional[str] = None
    officer_id: str
    date: str
    status: str = "active"                   # "active" | "reversed"
    reversed_by: Optional[str] = None
    reversed_reason: Optional[str] = None
    reversed_date: Optional[str] = None
