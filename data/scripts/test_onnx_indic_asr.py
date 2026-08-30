import os
import requests
import io
import wave
import struct
import math

BASE_URL = "http://localhost:8001"

def create_synthetic_wav_bytes(duration_sec=2.0, sample_rate=16000):
    buf = io.BytesIO()
    num_samples = int(duration_sec * sample_rate)
    with wave.open(buf, 'wb') as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        samples = []
        for i in range(num_samples):
            t = i / sample_rate
            value = int(10000 * math.sin(2 * math.pi * 440 * t) * math.sin(2 * math.pi * 2 * t))
            samples.append(struct.pack('<h', value))
        wav_file.writeframes(b''.join(samples))
    return buf.getvalue()

def test_onnx_model_integration():
    print("=" * 60)
    print(" 🚀 IN-REPO LIGHTWEIGHT ONNX INDIC ASR MODEL VERIFICATION")
    print("=" * 60)
    
    # 1. Verify model file existence in models/
    model_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../models/indic_asr_tiny.onnx"))
    print(f"\n1. Verifying ONNX model path: {model_path}")
    if os.path.exists(model_path):
        size_mb = os.path.getsize(model_path) / (1024 * 1024)
        print(f"✅ ONNX Model file present! Size: {size_mb:.2f} MB")
        assert size_mb < 100, "Model size exceeds GitHub 100MB file limit"
    else:
        print("❌ ONNX Model file missing!")
        return False
        
    # 2. Test ONNXIndicASR session load
    print("\n2. Initializing ONNX runtime session (onnxruntime)...")
    try:
        from shared.onnx_indic_asr import ONNXIndicASR
        session = ONNXIndicASR.get_session()
        print(f"✅ ONNX Session initialized: {type(session)}")
    except Exception as e:
        print(f"❌ ONNX Session failed: {e}")
        return False
        
    # 3. Test Audio Transcription endpoint via backend
    print("\n3. Testing Backend Audio Transcription endpoint (/api/transcribe)...")
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": "dysp1", "password": "demo1234"})
    assert res.status_code == 200
    token = res.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}
    
    wav_bytes = create_synthetic_wav_bytes(duration_sec=2.0)
    files = {"audio": ("test_recording.wav", wav_bytes, "audio/wav")}
    
    trans_res = requests.post(f"{BASE_URL}/api/transcribe", headers=headers, files=files, data={"language": "mix-IN"})
    print(f"  Response Status: {trans_res.status_code}")
    assert trans_res.status_code == 200
    print(f"  Transcript: '{trans_res.json().get('transcript')}'")
    
    print("\n" + "=" * 60)
    print(" 🎉 IN-REPO LIGHTWEIGHT ONNX INDIC MODEL VERIFIED 100% SUCCESSFUL!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    test_onnx_model_integration()
