import urllib.request
import json
import asyncio
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

def fetch_hinglish_samples(limit=15):
    url = f"https://datasets-server.huggingface.co/rows?dataset=ujs/hinglish-compressed&config=default&split=train&limit={limit}"
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    try:
        with urllib.request.urlopen(req) as res:
            data = json.loads(res.read().decode())
            rows = data.get('rows', [])
            samples = []
            for r in rows:
                row_data = r.get('row', {})
                sentence = row_data.get('sentence', '')
                audio_info = row_data.get('audio', [{}])[0]
                samples.append({
                    'path': row_data.get('path', ''),
                    'sentence': sentence,
                    'audio_url': audio_info.get('src', '')
                })
            return samples
    except Exception as e:
        print(f"Error fetching dataset rows: {e}")
        return []

async def run_evaluation():
    # Login to local API endpoint to use normalizer with proper authentication
    import urllib.request
    login_url = "http://localhost:8001/api/auth/login"
    login_data = json.dumps({"username": "dysp1", "password": "demo1234"}).encode()
    login_req = urllib.request.Request(login_url, data=login_data, headers={"Content-Type": "application/json"})
    
    try:
        with urllib.request.urlopen(login_req) as res:
            token_data = json.loads(res.read().decode())
            token = token_data["token"]
    except Exception as e:
        print(f"Failed to authenticate with local backend: {e}")
        return

    print("Fetching samples from HuggingFace dataset 'ujs/hinglish-compressed'...")
    samples = fetch_hinglish_samples(12)
    print(f"Fetched {len(samples)} samples.\n")

    results = []
    print("=" * 100)
    print("HINGLISH VOICE NORMALIZATION EVALUATION REPORT")
    print("Dataset: ujs/hinglish-compressed (HuggingFace)")
    print("=" * 100)

    for idx, sample in enumerate(samples, 1):
        raw_text = sample['sentence']
        norm_url = "http://localhost:8001/api/transcribe/normalize"
        norm_payload = json.dumps({"text": raw_text, "language": "mix-IN"}).encode()
        norm_req = urllib.request.Request(
            norm_url,
            data=norm_payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}"
            }
        )
        try:
            with urllib.request.urlopen(norm_req) as res:
                norm_data = json.loads(res.read().decode())
                normalized = norm_data.get("normalized_text", raw_text)
        except Exception as e:
            normalized = f"Error: {e}"

        results.append({
            'sample_id': idx,
            'audio_path': sample['path'],
            'original_hinglish': raw_text,
            'normalized_english': normalized
        })
        print(f"Sample #{idx}:")
        print(f"  Input (Hinglish):  {raw_text}")
        print(f"  Output (Normalized): {normalized}")
        print("-" * 100)

    return results

if __name__ == "__main__":
    asyncio.run(run_evaluation())
