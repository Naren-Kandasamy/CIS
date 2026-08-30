import io
import torch
from transformers import pipeline

print("Loading HuggingFace Indic Code-Switching ASR Pipeline...")
try:
    # Use lightweight Wav2Vec2 / Whisper model for fast Indic speech recognition
    asr_pipeline = pipeline(
        "automatic-speech-recognition",
        model="openai/whisper-tiny",  # or Indic-ASR / Hinglish model
        device=0 if torch.cuda.is_available() else -1
    )
    print("ASR Pipeline loaded successfully!")
except Exception as e:
    print(f"Error loading ASR pipeline: {e}")
