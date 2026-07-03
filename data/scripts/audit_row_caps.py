import json
import os

def audit_ztsql_rows():
    file_path = os.path.join(os.path.dirname(__file__), "../story_firs.json")
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find {file_path}")
        return
        
    with open(file_path, "r") as f:
        firs = json.load(f)
        
    num_firs = len(firs)
    num_accused = sum(len(fir.get("accused_ids", [])) for fir in firs)
    num_victims = sum(len(fir.get("victim_ids", [])) for fir in firs)
    
    unique_districts = set(fir.get("district_name") for fir in firs if fir.get("district_name"))
    num_units = len(unique_districts) * 5 # Approximation: 5 police stations per district
    
    print("="*50)
    print(" ZTSQL ROW CAP AUDIT (Catalyst Dev Tier)")
    print("="*50)
    print(f"Total FIRs in dataset: {num_firs}\n")
    
    print("Estimated Rows per Table:")
    print(f" - 'cases' table:   {num_firs:5d} rows")
    print(f" - 'accused' table: {num_accused:5d} rows")
    print(f" - 'victims' table: {num_victims:5d} rows")
    print(f" - 'units' table:   {num_units:5d} rows")
    
    total_rows = num_firs + num_accused + num_victims + num_units
    
    print("-" * 50)
    print(f"Total Project Rows: {total_rows}")
    print("\nCatalyst Development Tier Constraints:")
    print(" - Max Rows per Table:   5,000")
    print(" - Max Rows per Project: 25,000")
    
    print("\nAudit Results:")
    warnings = 0
    if num_firs >= 5000:
        print(" ❌ WARNING: 'cases' table exceeds or hits the 5,000 row cap!")
        warnings += 1
    if num_accused >= 5000:
        print(" ❌ WARNING: 'accused' table exceeds or hits the 5,000 row cap!")
        warnings += 1
    if total_rows >= 25000:
        print(" ❌ WARNING: Total project rows exceed the 25,000 cap!")
        warnings += 1
        
    if warnings == 0:
        print(" ✅ PASSED: Dataset comfortably fits within Catalyst ZTSQL Development Tier limits.")
        
if __name__ == "__main__":
    audit_ztsql_rows()
