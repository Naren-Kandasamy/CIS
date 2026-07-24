# PS-1 Phase 5, Item 1.2: Review Queue Item Models
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.2.

from pydantic import BaseModel
from typing import Literal, Optional

# FIXED S-1: item_type is now a Literal so Pydantic raises ValidationError
# at construction time for any unknown type string.
REVIEW_ITEM_TYPE = Literal[
    "cold_case_match",
    "contradiction_alert",
    "anpr_wanted_hit",
    "interstate_handoff",
]

class ReviewQueueItem(BaseModel):
    item_id: str
    item_type: REVIEW_ITEM_TYPE       # must be one of the four defined alert types
    fir_id: str
    related_fir_id: Optional[str] = None    # e.g. the matched cold case
    accused_id: Optional[str] = None
    summary: str                            # short, human-readable, deterministic template string
    score: Optional[float] = None           # match/confidence score, if applicable
    created_date: str                       # ISO datetime string
    status: str = "pending"                 # "pending" | "reviewed" | "dismissed"
    reviewed_by: Optional[str] = None
    reviewed_date: Optional[str] = None
