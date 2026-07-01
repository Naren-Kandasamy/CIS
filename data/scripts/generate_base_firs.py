import json
import os
import random
from datetime import datetime, timedelta
import uuid

def load_distributions(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

def random_date(start_year=2020, end_year=2024):
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    delta = end_date - start_date
    random_days = random.randrange(delta.days)
    return start_date + timedelta(days=random_days)

def generate_firs(distributions, num_firs=3500):
    districts = distributions["districts"]
    crime_sub_heads = distributions["crime_sub_heads"]
    
    # Pre-calculate weights for choices
    csh_weights = [csh["weight"] for csh in crime_sub_heads]
    
    firs = []
    
    for i in range(num_firs):
        # 1-digit category (1 for FIR) + 4-digit dist + 4-digit unit + 4-digit year + 5-digit serial
        category = "1"
        district_id = str(random.randint(1000, 9999))
        unit_id = str(random.randint(1000, 9999))
        
        incident_date = random_date()
        year = str(incident_date.year)
        serial = f"{i+1:05d}"
        
        crime_no = f"{category}{district_id}{unit_id}{year}{serial}"
        
        csh = random.choices(crime_sub_heads, weights=csh_weights, k=1)[0]
        
        fir = {
            "fir_internal_id": str(uuid.uuid4()),
            "crime_no": crime_no,
            "district_name": random.choice(districts),
            "incident_date": incident_date.strftime("%Y-%m-%d"),
            "crime_head_id": csh["head_id"],
            "crime_sub_head_id": csh["id"],
            "crime_sub_head_name": csh["name"],
            # To be populated in Phase 3/4
            "accused_ids": [],
            "victim_ids": [],
            "narrative": "",
            "mo_descriptor": ""
        }
        firs.append(fir)
        
    return firs

def main():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    dist_path = os.path.join(base_dir, "crime_distributions.json")
    out_path = os.path.join(base_dir, "base_firs.json")
    
    if not os.path.exists(dist_path):
        print("❌ crime_distributions.json not found! Run extract_distributions.py first.")
        return
        
    print("[*] Loading distributions...")
    dists = load_distributions(dist_path)
    
    print(f"[*] Generating 3500 base FIRs...")
    firs = generate_firs(dists, 3500)
    
    with open(out_path, "w") as f:
        json.dump(firs, f, indent=4)
        
    print(f"✅ Successfully wrote {len(firs)} FIRs to {out_path}")

if __name__ == "__main__":
    random.seed(42) # For reproducibility
    main()
