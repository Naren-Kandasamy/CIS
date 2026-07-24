import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, timedelta, date
from shared.data_sources.inject_pattern_registry import pattern_registry
from shared.financial_suspicion import compute_structuring_suspicion

# We need to import the providers so they register their patterns
import shared.data_sources.synthetic_cdr
import shared.data_sources.synthetic_financial
import shared.data_sources.synthetic_anpr

def test_financial_suspicion():
    print("--- Testing Financial Suspicion Logic ---")
    # 1. Benign transactions
    benign_txns = pattern_registry.run("benign_financial", account_id="acct_benign123")
    score_benign = compute_structuring_suspicion(benign_txns)
    print(f"Benign Account Suspicion Score: {score_benign:.3f} (expected near 0.0)")

    # 2. Structuring transactions (CTR)
    struct_txns = pattern_registry.run("structuring", profile_name="structuring_ctr", source_account="acct_sus123", total_amount=2500000)
    # We only want the first hop from the source account for scoring the source
    source_txns = [t for t in struct_txns if t["from_account"] == "acct_sus123"]
    score_struct = compute_structuring_suspicion(source_txns)
    print(f"Structuring Account Suspicion Score: {score_struct:.3f} (expected high)")

def test_cdr_patterns():
    print("\n--- Testing CDR Patterns ---")
    incident_time = datetime.utcnow()
    burner_calls = pattern_registry.run("burner_phone", incident_time=incident_time, phone_a="+919876543210", phone_b="+918765432109", tower_near_incident="TWR-45")
    print(f"Burner phone generated {len(burner_calls)} calls")

    silent_meetup = pattern_registry.run("silent_meetup", phone_a="+911111111111", phone_b="+912222222222", tower_id="TWR-99", meetup_dates=[date.today()])
    print(f"Silent meetup generated {len(silent_meetup)} ping records")
    print(f"Silent meetup CALLED edges check: {any('callee' in r for r in silent_meetup)} (expected False)")

def test_anpr_patterns():
    print("\n--- Testing ANPR Patterns ---")
    incident_time = datetime.utcnow()
    recce = pattern_registry.run("anpr_recce", plate_number="KA-01-AB-1234", camera_id="CAM-50", incident_time=incident_time)
    print(f"Recce generated {len(recce)} plate reads")
    
if __name__ == "__main__":
    test_financial_suspicion()
    test_cdr_patterns()
    test_anpr_patterns()
    
    print("\n--- Ground Truth Log ---")
    for log in pattern_registry.get_log():
        print(f"Injected {log['pattern_name']} -> {log['status']}")
