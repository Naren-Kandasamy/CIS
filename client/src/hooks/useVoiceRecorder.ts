import { useRef, useState } from 'react';
import { normalizeTranscript, transcribe } from '../lib/api';
import { AudioRecorderVAD } from '../lib/audioRecorder';
import { IndicSpeechRecognizer, type IndicLanguageCode } from '../lib/indicSpeech';
import type { QueryLanguage } from '../types/chat';

// Voice input, integrated from Hemnath's feat/indic-asr onto the redesigned
// chat components. Two capture paths:
//
//   • Primary — the browser Web Speech API (IndicSpeechRecognizer) transcribes
//     live in the browser; final text is sent to POST /api/transcribe/normalize
//     for police-station / IPC-section / code-mixed cleanup.
//   • Fallback — no SpeechRecognition (Firefox, locked-down Chromium): record
//     16 kHz WAV via AudioRecorderVAD, upload to POST /api/transcribe (Zia +
//     the cloud cascade), then normalize.
//
// AudioRecorderVAD always runs alongside the recognizer to feed the
// VoiceVisualizer's analyser (and, in fallback mode, to capture the audio).

interface UseVoiceRecorderArgs {
  /** Voice-input language code, e.g. "kn-IN" | "hi-IN" | "mix-IN". */
  language: IndicLanguageCode;
  /** Receives the full transcript to place in the input box (replaces, not appends). */
  onTranscript: (text: string) => void;
}

export interface VoiceRecorder {
  isRecording: boolean;
  isPaused: boolean;
  isTranscribing: boolean;
  /** True only in the WAV-upload fallback path, where pause/resume is meaningful. */
  canPause: boolean;
  /** Toggle: start listening, or stop + normalize if already listening. */
  toggleRecording: () => Promise<void>;
  togglePause: () => void;
  getAnalyser: () => AnalyserNode | null;
}

// The pipeline (/api/query) only understands en|hi|kn.
const toQueryLanguage = (v: IndicLanguageCode): QueryLanguage =>
  v.startsWith('kn') ? 'kn' : v.startsWith('hi') ? 'hi' : 'en';

export function useVoiceRecorder({ language, onTranscript }: UseVoiceRecorderArgs): VoiceRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [canPause, setCanPause] = useState(false);

  const vadRef = useRef<AudioRecorderVAD | null>(null);
  const recognizerRef = useRef<IndicSpeechRecognizer | null>(null);
  const lastTextRef = useRef('');

  const normalizeAndEmit = async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setIsTranscribing(true);
    try {
      const { normalized_text } = await normalizeTranscript(trimmed, language);
      onTranscript(normalized_text || trimmed);
    } catch {
      onTranscript(trimmed); // keep the raw transcript on failure
    } finally {
      setIsTranscribing(false);
    }
  };

  const stopAll = () => {
    recognizerRef.current?.stop();
    recognizerRef.current = null;
    setIsRecording(false);
    setIsPaused(false);
  };

  const toggleRecording = async () => {
    if (isRecording) {
      const usedRecognizer = recognizerRef.current !== null;
      const vad = vadRef.current;
      vadRef.current = null;
      stopAll();

      if (usedRecognizer) {
        await normalizeAndEmit(lastTextRef.current);
        if (vad) { try { await vad.stop(); } catch { /* ignore */ } }
        return;
      }
      // Fallback path: transcribe the captured WAV, then normalize.
      if (!vad) return;
      setIsTranscribing(true);
      try {
        const blob = await vad.stop();
        const { transcript } = await transcribe(blob, toQueryLanguage(language));
        await normalizeAndEmit(transcript);
      } catch {
        /* leave the input as-is */
      } finally {
        setIsTranscribing(false);
      }
      return;
    }

    // ── start ──────────────────────────────────────────────────────────────
    lastTextRef.current = '';
    try {
      const vad = new AudioRecorderVAD();
      vadRef.current = vad;
      await vad.start({ onAutoStop: () => { void toggleRecording(); } });
    } catch {
      vadRef.current = null; // mic denied — recognizer may still work
    }

    if (IndicSpeechRecognizer.isSupported()) {
      setCanPause(false);
      const recognizer = new IndicSpeechRecognizer(language);
      recognizerRef.current = recognizer;
      setIsRecording(true);
      setIsPaused(false);
      recognizer.start({
        onResult: (transcript) => {
          lastTextRef.current = transcript;
          onTranscript(transcript);
        },
        onError: () => stopAll(),
        onEnd: () => setIsRecording(false),
      });
    } else if (vadRef.current) {
      setCanPause(true);
      setIsRecording(true);
      setIsPaused(false);
    } else {
      setIsRecording(false); // nothing available
    }
  };

  const togglePause = () => {
    const vad = vadRef.current;
    if (!vad || !canPause) return;
    if (vad.isPaused()) {
      vad.resume();
      setIsPaused(false);
    } else {
      vad.pause();
      setIsPaused(true);
    }
  };

  const getAnalyser = () => vadRef.current?.getAnalyser() ?? null;

  return { isRecording, isPaused, isTranscribing, canPause, toggleRecording, togglePause, getAnalyser };
}
