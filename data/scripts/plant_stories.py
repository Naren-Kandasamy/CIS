import json
import os
import random
import uuid
from datetime import datetime, timedelta

def random_date(start_year=2020, end_year=2024):
    start_date = datetime(start_year, 1, 1)
    end_date = datetime(end_year, 12, 31)
    delta = end_date - start_date
    random_days = random.randrange(delta.days)
    return start_date + timedelta(days=random_days)

def generate_stories(base_firs, num_stories=500):
    """
    Generate 500 FIRs with planted stories (overlapping accused, shared MOs).
    """
    story_firs = []
    
    # Let's create a pool of 50 repeat offenders with Indian structured data
    banks = ["SBIN", "HDFC", "ICIC", "PUNB", "UTIB", "CNRB", "BOFA"]
    repeat_offenders = []
    for i in range(50):
        phone = f"+91{random.choice([9,8,7,6])}{random.randint(100000000, 999999999)}"
        acc = f"{random.choice(banks)}{random.randint(1000, 9999):04d}{random.randint(100000, 999999):06d}"
        rto = f"{random.randint(1, 73):02d}" # Karnataka RTO 01 to 73
        plate = f"KA-{rto}-{random.choice(['A','AB','M','Z','KA','C','F'])}-{random.randint(1,9999):04d}"
        
        repeat_offenders.append({
            "id": f"ACC-STORY-{i:03d}",
            "phone": phone,
            "bank_account": acc,
            "license_plate": plate
        })
    
    districts = list(set([f.get("district_name", "Bengaluru City") for f in base_firs]))
    
    for i in range(num_stories):
        category = "1"
        district_id = str(random.randint(1000, 9999))
        unit_id = str(random.randint(1000, 9999))
        incident_date = random_date()
        year = str(incident_date.year)
        serial = f"{3500 + i + 1:05d}"
        crime_no = f"{category}{district_id}{unit_id}{year}{serial}"
        
        # Pick 1-3 repeat offenders for this FIR
        accused_list = random.sample(repeat_offenders, k=random.randint(1, 3))
        accused_ids = [a["id"] for a in accused_list]
        phones = [a["phone"] for a in accused_list]
        accounts = [a["bank_account"] for a in accused_list]
        plates = [a["license_plate"] for a in accused_list]
        
        narrative = (f"During investigation of case {crime_no}, the suspects were found to be operating in the area. "
                     f"Technical intelligence indicated the use of mobile numbers {', '.join(phones)}. "
                     f"A vehicle with registration {', '.join(plates)} was seen fleeing the scene. "
                     f"Financial tracing identified suspicious transfers to account {accounts[0]}.")
        
        fir = {
            "fir_internal_id": str(uuid.uuid4()),
            "crime_no": crime_no,
            "district_name": random.choice(districts) if districts else "Bengaluru City",
            "incident_date": incident_date.strftime("%Y-%m-%d"),
            "crime_head_id": "CH002", # Crimes Against Property
            "crime_sub_head_id": "CSH004", # Robbery
            "crime_sub_head_name": "Robbery",
            "accused_ids": accused_ids,
            "victim_ids": [f"VIC-STORY-{uuid.uuid4().hex[:6]}"],
            "narrative": narrative,
            "mo_descriptor": "Group operation utilizing vehicles and coordinated communication.",
            "entities": {
                "phones": phones,
                "bank_accounts": accounts,
                "license_plates": plates
            }
        }
        story_firs.append(fir)
        
    return story_firs

def main():
    base_dir = os.path.dirname(os.path.dirname(__file__))
    base_firs_path = os.path.join(base_dir, "base_firs.json")
    out_path = os.path.join(base_dir, "story_firs.json")
    
    if not os.path.exists(base_firs_path):
        print("❌ base_firs.json not found! Run generate_base_firs.py first.")
        return
        
    print("[*] Loading base FIRs...")
    with open(base_firs_path, 'r') as f:
        base_firs = json.load(f)
        
    print("[*] Planting stories (500 FIRs with overlapping accused)...")
    story_firs = generate_stories(base_firs, 500)
    
    # Combine them for the next stage
    combined = base_firs + story_firs
    
    with open(out_path, "w") as f:
        json.dump(combined, f, indent=4)
        
    print(f"✅ Successfully wrote {len(combined)} combined FIRs to {out_path}")

if __name__ == "__main__":
    random.seed(42)
    main()
