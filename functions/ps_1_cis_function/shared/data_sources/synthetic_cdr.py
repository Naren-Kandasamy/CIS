import random
from datetime import datetime, timedelta, date
from shared.data_sources.base import CDRProvider
from shared.data_sources.inject_pattern_registry import pattern_registry

class SyntheticCDRProvider(CDRProvider):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_call_records(self, phone_number: str, start: datetime, end: datetime) -> list[dict]:
        records = []
        n_calls = self.rng.randint(5, 40)
        for _ in range(n_calls):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            records.append({
                "caller": phone_number,
                "callee": f"+91{self.rng.randint(7000000000, 9999999999)}",
                "timestamp": ts.isoformat(),
                "duration_sec": self.rng.randint(10, 900),
                "tower_id": f"TWR-{self.rng.randint(1, 200)}",
                "source_provenance": "synthetic_demo",
            })
        return records

    async def fetch_ping_records(self, phone_number: str, start: datetime, end: datetime) -> list[dict]:
        records = []
        n_pings = self.rng.randint(10, 50)
        for _ in range(n_pings):
            ts = start + timedelta(seconds=self.rng.randint(0, int((end - start).total_seconds())))
            records.append({
                "phone_number": phone_number,
                "tower_id": f"TWR-{self.rng.randint(1, 200)}",
                "timestamp": ts.isoformat(),
                "source_provenance": "synthetic_demo",
            })
        return records

    async def fetch_device_usage(self, imei: str, start: datetime, end: datetime) -> list[dict]:
        # Minimal background noise implementation, focus is on the deterministic injection
        return []

def inject_burner_pattern(incident_time: datetime, phone_a: str, phone_b: str, tower_near_incident: str, num_calls: int = 7, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    window_start = incident_time - timedelta(hours=48)
    window_end = incident_time + timedelta(hours=6)
    for _ in range(num_calls):
        ts = window_start + timedelta(seconds=rng.randint(0, int((window_end - window_start).total_seconds())))
        records.append({
            "caller": phone_a, "callee": phone_b,
            "timestamp": ts.isoformat(),
            "duration_sec": rng.randint(15, 300),
            "tower_id": tower_near_incident,
            "source_provenance": "synthetic_demo",
        })
    return records

def inject_silent_meetup_pattern(phone_a: str, phone_b: str, tower_id: str, meetup_dates: list[date], window_minutes: int = 20, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    for meetup_date in meetup_dates:
        meetup_time = datetime.combine(meetup_date, datetime.min.time()) + timedelta(minutes=rng.randint(0, 24*60-1))
        for phone in (phone_a, phone_b):
            offset = rng.randint(-window_minutes, window_minutes)
            ts = meetup_time + timedelta(minutes=offset)
            records.append({
                "phone_number": phone,
                "tower_id": tower_id,
                "timestamp": ts.isoformat(),
                "source_provenance": "synthetic_demo"
            })
    return records

def inject_imei_churn_pattern(imei: str, phone_numbers: list[str], first_activation: datetime, gap_days: tuple[int, int] = (2, 10), seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    current_start = first_activation
    for phone in phone_numbers:
        active_days = rng.randint(15, 45)
        deactivated_at = current_start + timedelta(days=active_days)
        records.append({
            "imei": imei,
            "phone_number": phone,
            "activated_at": current_start.isoformat(),
            "deactivated_at": deactivated_at.isoformat(),
            "source_provenance": "synthetic_demo"
        })
        current_start = deactivated_at + timedelta(days=rng.randint(*gap_days))
    return records

pattern_registry.register("burner_phone", inject_burner_pattern)
pattern_registry.register("silent_meetup", inject_silent_meetup_pattern)
pattern_registry.register("imei_churn", inject_imei_churn_pattern)
