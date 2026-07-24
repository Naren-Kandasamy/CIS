# PS-1 Phase 5, Item 1.2: Review Queue Item Models
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.2.

from pydantic import BaseModel
from typing import Optional

class ReviewQueueItem(BaseModel):
    item_id: str
    item_type: str            # "cold_case_match" | "contradiction_alert" | "anpr_wanted_hit" | "interstate_handoff"
    fir_id: str
    related_fir_id: Optional[str] = None    # e.g. the matched cold case
    accused_id: Optional[str] = None
    summary: str                            # short, human-readable, deterministic template string
    score: Optional[float] = None           # match/confidence score, if applicable
    created_date: str                       # ISO datetime string
    status: str = "pending"                 # "pending" | "reviewed" | "dismissed"
    reviewed_by: Optional[str] = None
    reviewed_date: Optional[str] = None
