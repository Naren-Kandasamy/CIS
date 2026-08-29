import { useRef, useState } from 'react';
import { transcribe } from '../lib/api';
import { startWavRecording, type WavRecorder } from '../lib/wavRecorder';
import type { QueryLanguage } from '../types/chat';

// Phase 3: mic / transcribe / pause flow lifted verbatim out of SessionChatPage
// (originally App.tsx:272-338). Behaviour is unchanged -- `onTranscript` receives
// the recognised text so the caller can append it to its input field.

interface UseVoiceRecorderArgs {
  language: QueryLanguage;
  onTranscript: (text: string) => void;
}

export interface VoiceRecorder {
  isRecording: boolean;
  isPaused: boolean;
  isTranscribing: boolean;
  /** Toggle: start recording, or stop + transcribe if already recording. */
  toggleRecording: () => Promise<void>;
  togglePause: () => void;
  getAnalyser: () => AnalyserNode | null;
}

export function useVoiceRecorder({ language, onTranscript }: UseVoiceRecorderArgs): VoiceRecorder {
  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const wavRecorderRef = useRef<WavRecorder | null>(null);

  const toggleRecording = async () => {
    if (isRecording) {
      const recorder = wavRecorderRef.current;
      wavRecorderRef.current = null;
      setIsRecording(false);
      setIsPaused(false);
      if (!recorder) return;
      try {
        setIsTranscribing(true);
        const audioBlob = await recorder.stop();
        const { transcript } = await transcribe(audioBlob, language);
        onTranscript(transcript);
      } catch {
        /* keep the input as-is; officer can retype */
      } finally {
        setIsTranscribing(false);
      }
    } else {
      try {
        wavRecorderRef.current = await startWavRecording();
        setIsRecording(true);
        setIsPaused(false);
      } catch {
        /* mic permission denied */
      }
    }
  };

  const togglePause = () => {
    const recorder = wavRecorderRef.current;
    if (!recorder) return;
    if (recorder.isPaused()) {
      recorder.resume();
      setIsPaused(false);
    } else {
      recorder.pause();
      setIsPaused(true);
    }
  };

  const getAnalyser = () => wavRecorderRef.current?.getAnalyser() || null;

  return { isRecording, isPaused, isTranscribing, toggleRecording, togglePause, getAnalyser };
}
