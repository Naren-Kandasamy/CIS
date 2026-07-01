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
    
    # Let's create a pool of 50 repeat offenders
    repeat_offenders = [f"ACC-STORY-{i:03d}" for i in range(50)]
    
    districts = list(set([f["district_name"] for f in base_firs]))
    
    for i in range(num_stories):
        category = "1"
        district_id = str(random.randint(1000, 9999))
        unit_id = str(random.randint(1000, 9999))
        incident_date = random_date()
        year = str(incident_date.year)
        serial = f"{3500 + i + 1:05d}"
        crime_no = f"{category}{district_id}{unit_id}{year}{serial}"
        
        # Pick 1-3 repeat offenders for this FIR
        accused = random.sample(repeat_offenders, k=random.randint(1, 3))
        
        fir = {
            "fir_internal_id": str(uuid.uuid4()),
            "crime_no": crime_no,
            "district_name": random.choice(districts),
            "incident_date": incident_date.strftime("%Y-%m-%d"),
            "crime_head_id": "CH002", # Crimes Against Property
            "crime_sub_head_id": "CSH004", # Robbery
            "crime_sub_head_name": "Robbery",
            "accused_ids": accused,
            "victim_ids": [f"VIC-STORY-{uuid.uuid4().hex[:6]}"],
            "narrative": "",
            "mo_descriptor": ""
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
