import os
import io
import wave
import json
import math
import numpy as np
import onnxruntime as ort

MODELS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../models"))
MODEL_PATH = os.path.join(MODELS_DIR, "indic_asr_tiny.onnx")
VOCAB_PATH = os.path.join(MODELS_DIR, "vocab.json")

class ONNXIndicASR:
    _session = None
    _vocab = None

    @classmethod
    def get_session(cls):
        if cls._session is None:
            if not os.path.exists(MODEL_PATH):
                raise FileNotFoundError(f"ONNX Model not found at {MODEL_PATH}")
            try:
                opts = ort.SessionOptions()
                opts.intra_op_num_threads = 2
                opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
                cls._session = ort.InferenceSession(MODEL_PATH, opts, providers=["CPUExecutionProvider"])
                print(f"[ONNX INDIC ASR] Session loaded successfully from {MODEL_PATH}")
            except Exception as e:
                print(f"[ONNX INDIC ASR ERROR] Session load failed: {e}")
                cls._session = "FALLBACK"
        return cls._session

    @classmethod
    def get_vocab(cls) -> dict:
        if cls._vocab is None:
            if os.path.exists(VOCAB_PATH):
                try:
                    with open(VOCAB_PATH, "r", encoding="utf-8") as f:
                        cls._vocab = json.load(f)
                except Exception:
                    cls._vocab = {}
            else:
                cls._vocab = {}
        return cls._vocab

    @classmethod
    def compute_log_mel_spectrogram(cls, audio_data: np.ndarray, n_mels: int = 80, n_fft: int = 400, hop_length: int = 160) -> np.ndarray:
        """
        Computes 80-band Log-Mel Spectrogram features for 16kHz audio.
        Target shape: (1, 80, 3000) tensor.
        """
        # Ensure 1D float32 array
        if len(audio_data) == 0:
            return np.zeros((1, n_mels, 3000), dtype=np.float32)

        # STFT computation
        num_samples = len(audio_data)
        window = np.hanning(n_fft).astype(np.float32)
        n_frames = max(1, int((num_samples - n_fft) / hop_length) + 1)
        
        # Limit or pad to 3000 time frames (~30 seconds max)
        max_frames = 3000
        n_frames_to_compute = min(n_frames, max_frames)
        
        fft_bins = n_fft // 2 + 1
        stft_matrix = np.zeros((fft_bins, n_frames_to_compute), dtype=np.float32)
        
        for i in range(n_frames_to_compute):
            start = i * hop_length
            end = start + n_fft
            if end <= num_samples:
                chunk = audio_data[start:end] * window
            else:
                chunk = np.pad(audio_data[start:], (0, max(0, n_fft - (num_samples - start)))) * window
            
            fft_mag = np.abs(np.fft.rfft(chunk, n=n_fft))
            stft_matrix[:, i] = fft_mag ** 2

        # Triangular Mel Filter Bank (0 Hz to 8000 Hz)
        low_freq = 0.0
        high_freq = 8000.0
        mel_low = 2595.0 * math.log10(1.0 + low_freq / 700.0)
        mel_high = 2595.0 * math.log10(1.0 + high_freq / 700.0)
        mel_points = np.linspace(mel_low, mel_high, n_mels + 2)
        hz_points = 700.0 * (10.0 ** (mel_points / 2595.0) - 1.0)
        bin_points = np.floor((n_fft + 1) * hz_points / 16000.0).astype(int)

        fbanks = np.zeros((n_mels, fft_bins), dtype=np.float32)
        for m in range(1, n_mels + 1):
            f_m_minus = bin_points[m - 1]
            f_m = bin_points[m]
            f_m_plus = bin_points[m + 1]

            for k in range(f_m_minus, f_m):
                if f_m != f_m_minus:
                    fbanks[m - 1, k] = (k - bin_points[m - 1]) / (f_m - bin_points[m - 1])
            for k in range(f_m, f_m_plus):
                if f_m_plus != f_m:
                    fbanks[m - 1, k] = (bin_points[m + 1] - k) / (bin_points[m + 1] - f_m)

        mel_spectrogram = np.dot(fbanks, stft_matrix)
        mel_spectrogram = np.maximum(mel_spectrogram, 1e-5)
        log_mel = np.log10(mel_spectrogram)
        
        # Dynamic normalization to [-1, 1] range
        log_mel = (log_mel + 4.0) / 4.0

        # Construct final (1, 80, 3000) tensor
        output_tensor = np.zeros((1, n_mels, max_frames), dtype=np.float32)
        output_tensor[0, :, :n_frames_to_compute] = log_mel
        return output_tensor

    @classmethod
    def transcribe(cls, audio_bytes: bytes, language: str = "mix") -> str:
        """
        Full 80-Mel Spectrogram extraction + ONNX model execution + Token decoding.
        """
        if not audio_bytes:
            return ""

        # Parse WAV audio into float32 array
        try:
            buf = io.BytesIO(audio_bytes)
            with wave.open(buf, 'rb') as wav_file:
                nchannels = wav_file.getnchannels()
                sampwidth = wav_file.getsampwidth()
                framerate = wav_file.getframerate()
                nframes = wav_file.getnframes()
                raw_pcm = wav_file.readframes(nframes)

                if sampwidth == 2:
                    audio_data = np.frombuffer(raw_pcm, dtype=np.int16).astype(np.float32) / 32768.0
                else:
                    audio_data = np.frombuffer(raw_pcm, dtype=np.uint8).astype(np.float32) / 128.0 - 1.0

                if nchannels > 1:
                    audio_data = audio_data[::nchannels]
        except Exception as e:
            print(f"[ONNX AUDIO PARSE NOTE] {e}")
            return ""

        session = cls.get_session()
        if not session or session == "FALLBACK":
            return ""

        try:
            # 1. Compute 80-channel log-mel features
            log_mel_features = cls.compute_log_mel_spectrogram(audio_data)
            
            # 2. Run ONNX Session Inference
            input_name = session.get_inputs()[0].name
            outputs = session.run(None, {input_name: log_mel_features})

            # 3. Process logits & predicted tokens
            if outputs and len(outputs) > 0:
                logits = outputs[0]
                if isinstance(logits, np.ndarray) and logits.size > 0:
                    predicted_ids = np.argmax(logits, axis=-1).flatten()
                    
                    # 4. Decode tokens using vocabulary dictionary
                    vocab = cls.get_vocab()
                    token_map = vocab.get("tokens", {})
                    
                    decoded_words = []
                    last_id = None
                    for token_id in predicted_ids:
                        token_str = str(int(token_id))
                        if token_str in token_map:
                            word = token_map[token_str]
                            if word and word != last_id:
                                decoded_words.append(word)
                                last_id = word
                                
                    transcript = " ".join(decoded_words).strip()
                    if transcript:
                        print(f"[ONNX DECODER SUCCESS] Transcribed: '{transcript}'")
                        return transcript
        except Exception as ex:
            print(f"[ONNX DECODER NOTE] {ex}")

        return ""
