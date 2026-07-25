import json

firs = json.load(open('data/story_firs.json'))
print("Keys:", firs[0].keys())
print("Accused IDs:", firs[0].get('accused_ids'))
print("Victim IDs:", firs[0].get('victim_ids'))
print("First FIR ID:", firs[0]['fir_internal_id'])
