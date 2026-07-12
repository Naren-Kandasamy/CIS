from pydantic import BaseModel, field_validator
from typing import Optional

DISTRICT_CANONICAL = {
    "mysore": "Mysuru", "mysuru": "Mysuru",
    "mandya": "Mandya",
    "bangalore": "Bengaluru", "bengaluru": "Bengaluru",
    "shimoga": "Shivamogga", "shivamogga": "Shivamogga",
    "hubli": "Hubballi", "hubballi": "Hubballi"
}

# NOTE: CRIME_TYPE_CANONICAL (free-text crime type normalization) is no
# longer the primary classification path -- the real schema uses
# CrimeHeadID -> CrimeSubHeadID lookups instead of a flat crime_type string
# (Implementation Section 17, Structural Difference #2). Kept here only as
# a fallback for free-text narrative parsing where no CrimeSubHeadID is
# available yet (e.g. raw OCR'd FIR text before classification).
CRIME_TYPE_CANONICAL = {
    "chain snatching": "chain_snatching",
    "chain-snatching": "chain_snatching",
    "burglary": "burglary", "house breaking": "burglary",
    "vehicle theft": "vehicle_theft", "auto theft": "vehicle_theft",
    "assault": "assault", "robbery": "robbery",
    "fraud": "fraud", "cheating": "fraud"
}

class VictimSchema(BaseModel):
    victim_id: str
    name: str
    age_years: Optional[int] = None
    gender_id: Optional[str] = None
    is_police: bool = False

class ComplainantSchema(BaseModel):
    complainant_id: str
    name: str
    age_years: Optional[int] = None
    occupation_id: Optional[str] = None
    # religion_id, caste_id deliberately omitted here -- see Implementation
    # Section 17 Open Decision 1. Add explicitly, with a documented reason,
    # if the team decides PS-1 should ingest these rather than dropping them
    # at the ingestion boundary.
    gender_id: Optional[str] = None

class AccusedSchema(BaseModel):
    accused_id: str
    name: str
    sort_label: Optional[str] = None  # "A1", "A2" -- display order from source data
    aliases: list[str] = []
    age_years: Optional[int] = None
    gender_id: Optional[str] = None
    tattoos: list[str] = []
    prior_fir_count: int = 0
    is_primary_accused: bool = True
    complainant_is_also_accused: bool = False

class ArrestSurrenderSchema(BaseModel):
    arrest_surrender_id: str
    accused_id: str
    arrest_or_surrender_type_id: Optional[str] = None
    arrest_surrender_date: Optional[str] = None
    arrest_district_id: Optional[str] = None  # can differ from the case's filing
                                                 # district -- Implementation Section 17
                                                 # Open Decision 3
    investigating_officer_id: Optional[str] = None

class FIRSchema(BaseModel):
    id: str                       # our surrogate key (fir_internal_id)
    crime_no: str                 # real KSP composite key -- see parse_crime_no()
    case_no: Optional[str] = None
    date: str                     # registered_date
    crime_head_id: Optional[str] = None      # major classification (was flat crime_type)
    crime_sub_head_id: Optional[str] = None  # minor classification (was flat crime_type)
    crime_type_freetext: Optional[str] = None  # fallback only, see CRIME_TYPE_CANONICAL note above
    district: str                 # derived via unit_id -> Unit -> DistrictID, not a source field directly
    unit_id: str                  # police station -- was "station" (flat string) before
    lat: Optional[float] = None
    lon: Optional[float] = None
    victims: list[VictimSchema] = []
    complainants: list[ComplainantSchema] = []
    accused: list[AccusedSchema] = []
    arrest_surrenders: list[ArrestSurrenderSchema] = []
    act_sections: list[tuple[str, str]] = []  # (act_code, section_code) pairs -- was flat ipc_sections string
    status: str = "open"
    mo_descriptor: str = ""
    narrative: Optional[str] = None
    ocr_extracted: bool = False

    @field_validator('district', mode='before')
    @classmethod
    def canonicalize_district(cls, v):
        return DISTRICT_CANONICAL.get(str(v).strip().lower(), str(v).strip())
