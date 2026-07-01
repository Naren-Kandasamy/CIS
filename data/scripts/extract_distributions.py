import json
import os

def generate_distributions():
    """
    Mock implementation of extract_distributions.py
    In a real scenario, this would scrape/parse NCRB data.
    For Phase 1, we output realistic distributions for Karnataka districts.
    """
    districts = ["Bengaluru", "Mysuru", "Mangaluru", "Hubballi", "Belagavi"]
    
    crime_heads = {
        "CH001": "Crimes Against Body",
        "CH002": "Crimes Against Property",
        "CH003": "Economic Offences"
    }

    crime_sub_heads = [
        {"id": "CSH001", "head_id": "CH001", "name": "Murder", "weight": 0.05},
        {"id": "CSH002", "head_id": "CH001", "name": "Assault", "weight": 0.25},
        {"id": "CSH003", "head_id": "CH002", "name": "Theft", "weight": 0.40},
        {"id": "CSH004", "head_id": "CH002", "name": "Robbery", "weight": 0.15},
        {"id": "CSH005", "head_id": "CH003", "name": "Fraud", "weight": 0.15},
    ]

    distributions = {
        "districts": districts,
        "crime_heads": crime_heads,
        "crime_sub_heads": crime_sub_heads,
        "years": [2020, 2021, 2022, 2023, 2024],
        "gender_ratio": {"M": 0.85, "F": 0.15},
        "age_distribution": {
            "18-25": 0.35,
            "26-35": 0.40,
            "36-45": 0.15,
            "46+": 0.10
        }
    }

    os.makedirs(os.path.dirname(__file__), exist_ok=True)
    out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "crime_distributions.json")
    
    with open(out_path, "w") as f:
        json.dump(distributions, f, indent=4)
        
    print(f"✅ Successfully wrote distributions to {out_path}")

if __name__ == "__main__":
    generate_distributions()
