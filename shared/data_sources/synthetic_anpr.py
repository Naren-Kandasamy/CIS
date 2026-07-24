"""
Synthetic ANPR Data Provider.
Generates camera plate-read events with authentic Indian registration formats and spatial coordinates.
See Docs/PS1_Extended_Investigative_Capabilities.md Section 5.
"""
import os
import json
import random
from datetime import datetime, timedelta
from shared.data_sources.base import ANPRProvider

SEED_FILE_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../data/seed/authentic_plates.json"))

class SyntheticANPRProvider(ANPRProvider):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)
        self.plates = self._load_seed_plates()

    def _load_seed_plates(self) -> list[str]:
        if os.path.exists(SEED_FILE_PATH):
            try:
                with open(SEED_FILE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if "authentic_plates" in data:
                        return data["authentic_plates"]
            except Exception:
                pass
        return ["KA 04 MB 8819", "MH 12 CD 5678", "TN 38 BY 1204", "DL 3C CJ 9012"]

    async def fetch_plate_reads(self, plate_number: str, start: datetime, end: datetime) -> list[dict]:
        reads = []
        # Generate 1 to 5 camera detection hits
        n_hits = self.rng.randint(1, 5)
        total_seconds = max(1, int((end - start).total_seconds()))
        
        for i in range(n_hits):
            ts = start + timedelta(seconds=self.rng.randint(0, total_seconds))
            reads.append({
                "plate_number": plate_number,
                "camera_id": f"CAM-BGLR-{self.rng.randint(101, 299)}",
                "lat": round(12.9716 + self.rng.uniform(-0.08, 0.08), 6),
                "lon": round(77.5946 + self.rng.uniform(-0.08, 0.08), 6),
                "timestamp": ts.isoformat(),
                "source_provenance": "synthetic_demo",
            })
        
        # Sort chronologically by timestamp
        reads.sort(key=lambda x: x["timestamp"])
        return reads
