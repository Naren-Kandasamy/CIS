"""
Pluggable Data Source Provider Interfaces.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 1.1.

Every record from every provider MUST carry explicit provenance:
  "source_provenance": "synthetic_demo" | "verified_legal_process"
"""
from abc import ABC, abstractmethod
from datetime import datetime

class ANPRProvider(ABC):
    @abstractmethod
    async def fetch_plate_reads(self, plate_number: str, start: datetime, end: datetime) -> list[dict]:
        """
        Returns list of plate read events:
        [{
            "plate_number": str,
            "camera_id": str,
            "lat": float,
            "lon": float,
            "timestamp": str (ISO 8601),
            "source_provenance": "synthetic_demo" | "verified_legal_process"
        }, ...]
        """
        pass
