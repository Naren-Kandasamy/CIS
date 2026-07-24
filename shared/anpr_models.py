"""
ANPR & Wanted Vehicle Models.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 5.2.
"""
from pydantic import BaseModel
from typing import Optional

class WantedVehicleRecord(BaseModel):
    plate_number: str
    reason: str                  # "stolen" | "linked_to_open_case" | "absconder_vehicle"
    fir_id: Optional[str] = None
    flagged_date: str
