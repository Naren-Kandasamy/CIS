import random
import math
from datetime import datetime, timedelta
from uuid import uuid4
from shared.data_sources.base import FinancialProvider
from shared.data_sources.inject_pattern_registry import pattern_registry

def generate_indian_account(rng: random.Random) -> str:
    banks = ["SBIN", "HDFC", "ICIC", "PUNB", "UTIB", "CNRB", "BOFA"]
    bank = rng.choice(banks)
    branch = f"{rng.randint(1000, 9999):04d}"
    acc = f"{rng.randint(100000, 999999):06d}"
    return f"{bank}{branch}{acc}"

def generate_indian_upi(rng: random.Random, phone: str = None) -> str:
    if not phone:
        phone = f"{rng.choice([9,8,7,6])}{rng.randint(100000000, 999999999)}"
    handles = ["@okicici", "@okhdfcbank", "@okaxis", "@ybl", "@sbi", "@paytm"]
    return f"{phone}{rng.choice(handles)}"

STRUCTURING_PROFILES = {
    "structuring_ctr":     {"threshold": 1000000, "chunk_margin": (10000, 50000)},
    "structuring_pan":     {"threshold": 50000,    "chunk_margin": (500, 5000)},
    "structuring_upi_cap": {"threshold": 100000,   "chunk_margin": (2000, 15000)},
}

class SyntheticFinancialProvider(FinancialProvider):
    def __init__(self, seed: int = 42):
        self.rng = random.Random(seed)

    async def fetch_transactions(self, account_id: str, start: datetime, end: datetime) -> list[dict]:
        # Baseline noise generation
        return []

def inject_structuring_pattern(profile_name: str, source_account: str, total_amount: int, num_hops: int = 3, hop_delay_minutes: int = 15, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    profile = STRUCTURING_PROFILES[profile_name]
    margin = rng.randint(*profile["chunk_margin"])
    chunk_size = profile["threshold"] - margin
    num_chunks = math.ceil(total_amount / chunk_size)
    
    # Base time in past 3 months
    base_time = datetime.utcnow() - timedelta(days=rng.randint(1, 90))
    records = []

    for i in range(num_chunks):
        if profile_name == "structuring_upi_cap":
            chain = [source_account] + [generate_indian_upi(rng) for _ in range(num_hops)]
        else:
            chain = [source_account] + [generate_indian_account(rng) for _ in range(num_hops)]
            
        amount = min(chunk_size, total_amount - i * chunk_size)
        ts = base_time + timedelta(minutes=i * hop_delay_minutes)
        for hop_index in range(len(chain) - 1):
            hop_ts = ts + timedelta(minutes=hop_index * hop_delay_minutes)
            records.append({
                "from_account": chain[hop_index],
                "to_account": chain[hop_index + 1],
                "amount": amount,
                "timestamp": hop_ts.isoformat(),
                "channel": "UPI" if profile_name == "structuring_upi_cap" else "NEFT",
                "pattern_tag": profile_name,
                "source_provenance": "synthetic_demo"
            })
    return records

def inject_smurfing_pattern(collection_account: str, total_amount: int, num_mules: int = 8, threshold: int = 50000, window_hours: int = 36, seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    per_mule = min(total_amount // num_mules, threshold - rng.randint(500, 5000))
    window_start = datetime.utcnow() - timedelta(days=rng.randint(1, 90))
    records = []
    
    for _ in range(num_mules):
        mule = generate_indian_account(rng)
        ts = window_start + timedelta(hours=rng.uniform(0, window_hours))
        records.append({
            "from_account": mule,
            "to_account": collection_account,
            "amount": per_mule,
            "timestamp": ts.isoformat(),
            "channel": "NEFT",
            "pattern_tag": "smurfing",
            "source_provenance": "synthetic_demo"
        })
    return records

def inject_benign_small_transactions(account_id: str, num_transactions: int = 15, amount_range: tuple = (500, 45000), seed: int = 42) -> list[dict]:
    rng = random.Random(seed)
    records = []
    for _ in range(num_transactions):
        channel = rng.choice(["UPI", "NEFT", "cash_deposit"])
        recipient = generate_indian_upi(rng) if channel == "UPI" else generate_indian_account(rng)
        amount = rng.randint(*amount_range)
        ts = datetime.utcnow() - timedelta(days=rng.randint(1, 180))
        records.append({
            "from_account": account_id,
            "to_account": recipient,
            "amount": amount,
            "timestamp": ts.isoformat(),
            "channel": rng.choice(["UPI", "NEFT", "cash_deposit"]),
            "pattern_tag": "None",
            "source_provenance": "synthetic_demo"
        })
    return records

pattern_registry.register("structuring", inject_structuring_pattern)
pattern_registry.register("smurfing", inject_smurfing_pattern)
pattern_registry.register("benign_financial", inject_benign_small_transactions)
