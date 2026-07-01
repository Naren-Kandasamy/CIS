import json
import sys

def validate_firs(filepath):
    print(f"[*] Validating {filepath}...")
    try:
        with open(filepath, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"❌ Failed to load JSON: {e}")
        sys.exit(1)
        
    total_firs = len(data)
    print(f"Total FIRs: {total_firs}")
    
    issues = []
    has_accused_count = 0
    empty_narrative_count = 0
    
    for i, fir in enumerate(data):
        # Check CrimeNo format
        crime_no = fir.get("crime_no", "")
        if len(crime_no) != 18 or not crime_no.isdigit():
            issues.append(f"Row {i}: Invalid crime_no format -> {crime_no}")
            
        # Check for narratives
        if not fir.get("narrative"):
            empty_narrative_count += 1
            
        # Check for accused
        if len(fir.get("accused_ids", [])) > 0:
            has_accused_count += 1
            
    print("\n--- Validation Report ---")
    if total_firs != 4000:
        print(f"⚠️ Expected 4000 FIRs, found {total_firs}.")
    else:
        print("✅ Correct number of FIRs (4000).")
        
    print(f"ℹ️ FIRs with populated narratives: {total_firs - empty_narrative_count} / {total_firs}")
    print(f"ℹ️ FIRs with accused IDs (Story FIRs): {has_accused_count}")
    
    if len(issues) == 0:
        print("✅ No structural issues found with Crime Numbers.")
    else:
        print(f"❌ Found {len(issues)} structural issues.")
        for iss in issues[:5]:
            print("  - " + iss)
        if len(issues) > 5:
            print(f"  ...and {len(issues) - 5} more.")
            
    if empty_narrative_count == 0 and has_accused_count >= 500:
        print("\n🏆 Dataset is robust and fully seeded! Ready for Database Ingestion (Phase 5).")
    else:
        print("\n⚠️ Note: The dataset has missing narratives or missing story accused.")

if __name__ == "__main__":
    validate_firs("/home/nkandasamy/Desktop/CIS/data/story_firs.json")
