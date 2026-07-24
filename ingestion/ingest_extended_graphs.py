import asyncio
import json
import random
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../')))

from shared.data_sources.inject_pattern_registry import pattern_registry
from ingestion.cdr_financial_ingest import (
    push_call_records_to_graph,
    push_ping_records_to_graph,
    push_financial_records_to_graph
)
from ingestion.anpr_ingest import push_anpr_records_to_graph
from shared.graph_client import close

# Import to register patterns
import shared.data_sources.synthetic_cdr
import shared.data_sources.synthetic_financial
import shared.data_sources.synthetic_anpr

async def main():
    file_path = os.path.join(os.path.dirname(__file__), "../data/story_firs.json")
    with open(file_path, "r") as f:
        firs = json.load(f)

    # Filter FIRs that actually have entities
    entity_firs = [f for f in firs if "entities" in f]
    print(f"Found {len(entity_firs)} FIRs with extended entities.")
    random.seed(42)
    
    # 1. Distribute patterns (5% - 10% of FIRs)
    financial_targets = random.sample(entity_firs, k=int(len(entity_firs) * 0.1))
    cdr_targets = random.sample(entity_firs, k=int(len(entity_firs) * 0.1))
    anpr_targets = random.sample(entity_firs, k=int(len(entity_firs) * 0.1))
    
    # 2. Inject Financial
    print(f"Generating financial patterns for {len(financial_targets)} FIRs...")
    all_financial = []
    for fir in financial_targets:
        accounts = fir["entities"].get("bank_accounts", [])
        if accounts:
            account = accounts[0]
            profile = random.choice(["structuring_ctr", "structuring_pan", "structuring_upi_cap"])
            txns = pattern_registry.run("structuring", profile_name=profile, source_account=account, total_amount=2500000)
            all_financial.extend(txns)
            
    # 3. Inject CDR
    print(f"Generating CDR patterns for {len(cdr_targets)} FIRs...")
    all_calls = []
    all_pings = []
    for fir in cdr_targets:
        phones = fir["entities"].get("phones", [])
        if len(phones) >= 2:
            incident_time = datetime.strptime(fir["incident_date"], "%Y-%m-%d")
            calls = pattern_registry.run("burner_phone", incident_time=incident_time, phone_a=phones[0], phone_b=phones[1], tower_near_incident="TWR-45")
            all_calls.extend(calls)
            
            pings = pattern_registry.run("silent_meetup", phone_a=phones[0], phone_b=phones[1], tower_id="TWR-99", meetup_dates=[incident_time.date()])
            all_pings.extend(pings)

    # 4. Inject ANPR
    print(f"Generating ANPR patterns for {len(anpr_targets)} FIRs...")
    all_anpr = []
    for fir in anpr_targets:
        plates = fir["entities"].get("license_plates", [])
        if plates:
            incident_time = datetime.strptime(fir["incident_date"], "%Y-%m-%d")
            reads = pattern_registry.run("anpr_recce", plate_number=plates[0], camera_id="CAM-50", incident_time=incident_time)
            all_anpr.extend(reads)
            
    # 5. Inject Benign Noise (True Negatives)
    print(f"Generating benign noise for {len(entity_firs)} FIRs...")
    for fir in entity_firs:
        for acc in fir["entities"].get("bank_accounts", []):
            benign_txns = pattern_registry.run("benign_financial", account_id=acc, num_transactions=random.randint(5, 15))
            all_financial.extend(benign_txns)
            
    print(f"Pushing {len(all_financial)} financial records in chunks...")
    for i in range(0, len(all_financial), 500):
        await push_financial_records_to_graph(all_financial[i:i+500])
        print(f"  -> Pushed financial records {i} to {min(i+500, len(all_financial))}")
        await asyncio.sleep(0.5)

    print(f"Pushing {len(all_calls)} call records in chunks...")
    for i in range(0, len(all_calls), 500):
        await push_call_records_to_graph(all_calls[i:i+500])
        print(f"  -> Pushed call records {i} to {min(i+500, len(all_calls))}")
        await asyncio.sleep(0.5)

    print(f"Pushing {len(all_pings)} ping records in chunks...")
    for i in range(0, len(all_pings), 500):
        await push_ping_records_to_graph(all_pings[i:i+500])
        print(f"  -> Pushed ping records {i} to {min(i+500, len(all_pings))}")
        await asyncio.sleep(0.5)

    print(f"Pushing {len(all_anpr)} ANPR records in chunks...")
    for i in range(0, len(all_anpr), 500):
        await push_anpr_records_to_graph(all_anpr[i:i+500])
        print(f"  -> Pushed ANPR records {i} to {min(i+500, len(all_anpr))}")
        await asyncio.sleep(0.5)
            
    print("Finished injecting extended graphs!")
    
    print("\nGround Truth Log Stats:")
    log = pattern_registry.get_log()
    print(f"Total patterns injected: {len(log)}")
    
    await close()

if __name__ == "__main__":
    asyncio.run(main())
