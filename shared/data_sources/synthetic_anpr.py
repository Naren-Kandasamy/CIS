import random
from datetime import datetime, timedelta
from shared.data_sources.base import ANPRProvider
from shared.data_sources.inject_pattern_registry import pattern_registry

def generate_karnataka_plate(rng: random.Random) -> str:
    rto = f"{rng.randint(1, 73):02d}"  # Karnataka has RTOs up to KA-73
    letters = rng.choice(["A", "AB", "M", "Z", "KA", "C", "F"])
    num = f"{rng.randint(1, 9999):04d}"
    return f"KA-{rto}-{letters}-{num}"

class SyntheticANPRProvider(ANPRProvider):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_plate_reads(self, plate_number: str, start: datetime, end: datetime) -> list[dict]:
        reads = []
        for _ in range(self.rng.randint(1, 10)):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            reads.append({
                "plate_number": plate_number,
                "camera_id": f"CAM-{self.rng.randint(1, 150)}",
                "lat": 12.9 + self.rng.uniform(-0.3, 0.3),
                "lon": 77.6 + self.rng.uniform(-0.3, 0.3),
                "timestamp": ts.isoformat(),
                "speed": self.rng.uniform(20.0, 80.0),
                "source_provenance": "synthetic_demo",
            })
        return reads

def inject_recce_pattern(plate_number: str, camera_id: str, incident_time: datetime, num_recce_visits: int = 4, lookback_days: int = 14, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    
    for _ in range(num_recce_visits):
        days_before = rng.randint(1, lookback_days)
        # Recce pattern expects odd hours
        visit_time = (incident_time - timedelta(days=days_before)).replace(
            hour=rng.choice([23, 0, 1, 2, 3]), minute=rng.randint(0, 59))
        records.append({
            "plate_number": plate_number,
            "camera_id": camera_id,
            "lat": 12.9 + rng.uniform(-0.01, 0.01),
            "lon": 77.6 + rng.uniform(-0.01, 0.01),
            "timestamp": visit_time.isoformat(),
            "speed": rng.uniform(15, 35),
            "source_provenance": "synthetic_demo"
        })
        
    incident_detection_time = incident_time + timedelta(minutes=rng.randint(-15, 15))
    records.append({
        "plate_number": plate_number,
        "camera_id": camera_id,
        "lat": 12.9 + rng.uniform(-0.01, 0.01),
        "lon": 77.6 + rng.uniform(-0.01, 0.01),
        "timestamp": incident_detection_time.isoformat(),
        "speed": rng.uniform(30, 60),
        "source_provenance": "synthetic_demo"
    })
    
    # Sort by time
    records.sort(key=lambda x: x["timestamp"])
    return records

pattern_registry.register("anpr_recce", inject_recce_pattern)
