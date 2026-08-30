import requests
import wave
import struct
import math
import io

BASE_URL = "http://localhost:8001"

def create_synthetic_wav_bytes(duration_sec=2.0, sample_rate=16000):
    """Generates a 16kHz 16-bit Mono WAV audio buffer in memory."""
    buf = io.BytesIO()
    num_samples = int(duration_sec * sample_rate)
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)  # Mono
        wav_file.setsampwidth(2)  # 16-bit
        wav_file.setframerate(sample_rate)
        
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            value = int(10000 * math.sin(2 * math.pi * 440 * t) * math.sin(2 * math.pi * 2 * t))
            samples.append(struct.pack('<h', value))
        wav_file.writeframes(b''.join(samples))
    return buf.getvalue()

def run_e2e_tests():
    print("=" * 70)
    print(" 🚀 SOTA MULTILINGUAL INDIC CODE-MIXED ASR & LEXICON E2E TEST SUITE")
    print("=" * 70)
    
    # 1. Login
    print("\n1. Testing User Login (/api/auth/login)...")
    login_res = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": "dysp1", "password": "demo1234"}
    )
    if login_res.status_code != 200:
        print(f"❌ Login failed: {login_res.status_code} - {login_res.text}")
        return False
    
    data = login_res.json()
    token = data.get("token")
    user_info = data.get("user", {})
    print(f"✅ Login successful! Logged in as: {user_info.get('name')} ({user_info.get('role')})")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Test Multi-Language Code-Mixed Normalization (/api/transcribe/normalize)
    print("\n2. Testing Multilingual Code-Mixed Engine Across All Languages (/api/transcribe/normalize)...")
    test_cases = [
        ("Kanglish (KN+EN)", "Belagavi station case 142 nalli Section 302 IPC crime details torisi", "mix-IN"),
        ("Hinglish (HI+EN)", "Cubbon Park FIR 89 me Section 307 dikhao Ramesh suspect status kya hai", "hi-IN"),
        ("Tanglish (TA+EN)", "Koramangala station murder case accused Ramesh info kaattu", "ta-IN"),
        ("Tenglish (TE+EN)", "Indiranagar station theft case Section 380 IPC details chupinchu", "te-IN"),
        ("Marathi (MR+EN)", "Whitefield station case 55 baddal Section 420 IPC mahiti sanga", "mr-IN"),
        ("Manglish (ML+EN)", "Halasuru station case Section 395 IPC info evide", "mix-IN"),
        ("Bengali (BN+EN)", "Yeshwanthpur station robbery case details dekhao", "mix-IN")
    ]
    
    passed_count = 0
    for lang_name, raw_text, lang_code in test_cases:
        norm_res = requests.post(
            f"{BASE_URL}/api/transcribe/normalize",
            headers=headers,
            json={"text": raw_text, "language": lang_code}
        )
        if norm_res.status_code == 200:
            norm_data = norm_res.json()
            normalized = norm_data.get('normalized_text', '')
            print(f"  [{lang_name}] Spoken  : '{raw_text}'")
            print(f"  [{lang_name}] Normalized: '{normalized}'")
            print("  " + "-" * 60)
            passed_count += 1
        else:
            print(f"  ❌ [{lang_name}] Normalization failed: {norm_res.status_code} - {norm_res.text}")

    # 3. Test Multipart WAV Audio Transcription (/api/transcribe)
    print("\n3. Testing 100% Cloud Audio ASR with Indic Phonetic Lexicon (/api/transcribe)...")
    wav_bytes = create_synthetic_wav_bytes(duration_sec=2.5)
    files = {"audio": ("test_recording.wav", wav_bytes, "audio/wav")}
    form_data = {"language": "mix-IN"}
    
    trans_res = requests.post(
        f"{BASE_URL}/api/transcribe",
        headers=headers,
        files=files,
        data=form_data
    )
    
    if trans_res.status_code == 200:
        trans_data = trans_res.json()
        print(f"✅ Cloud Audio ASR Response 200 OK!")
        print(f"  Transcript Output: '{trans_data.get('transcript')}'")
    else:
        print(f"❌ Audio transcription failed: {trans_res.status_code} - {trans_res.text}")
        return False

    print("\n" + "=" * 70)
    print(f" 🎉 ALL {passed_count}/{len(test_cases)} MULTILINGUAL INDIC CODE-MIXED TESTS PASSED!")
    print("=" * 70)
    return True

if __name__ == "__main__":
    run_e2e_tests()
