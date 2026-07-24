# PS-1 Phase 5, Item 7: Hypothesis Workspace
# See Docs/PS1_Extended_Investigative_Capabilities.md Section 7.2.

from pydantic import BaseModel
from typing import Optional, List

class HypothesisRecord(BaseModel):
    hypothesis_id: str
    fir_id: str
    officer_id: str
    statement: str                    # free text, officer-authored
    linked_entity_ids: List[str]      # accused_ids / fir_ids / person_ids referenced
    status: str = "open"              # "open" | "confirmed" | "refuted"
    created_date: str                 # ISO datetime
    resolved_by: Optional[str] = None
    resolved_reason: Optional[str] = None
    resolved_date: Optional[str] = None

class HypothesisCheckLog(BaseModel):
    check_id: str
    hypothesis_id: str
    checked_date: str                 # ISO datetime
    new_supporting_evidence_count: int
    new_contradicting_evidence_count: int
    notes: str                        # deterministic summary
