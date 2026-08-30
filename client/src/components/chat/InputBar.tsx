import React, { useState } from 'react';
import { Mic, Pause, Paperclip, Send } from 'lucide-react';
import { VoiceVisualizer } from './VoiceVisualizer';
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder';
import { INDIC_LANGUAGES, type IndicLanguageCode } from '../../lib/indicSpeech';
import type { QueryLanguage } from '../../types/chat';

// Phase 3: the composer -- text field, voice-input language select, mic + send,
// and the recording status strip. The mic flow (browser SpeechRecognition +
// server normalize, WAV-upload fallback) lives in useVoiceRecorder.

interface InputBarProps {
  disabled: boolean;
  onSend: (text: string, language: QueryLanguage) => void | Promise<void>;
}

// The 7 voice-input codes fold down to the pipeline's en|hi|kn.
const toQueryLanguage = (v: IndicLanguageCode): QueryLanguage =>
  v.startsWith('kn') ? 'kn' : v.startsWith('hi') ? 'hi' : 'en';

export function InputBar({ disabled, onSend }: InputBarProps) {
  const [inputValue, setInputValue] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState<IndicLanguageCode>('en-IN');

  const {
    isRecording,
    isPaused,
    isTranscribing,
    canPause,
    toggleRecording,
    togglePause,
    getAnalyser,
  } = useVoiceRecorder({
    language: voiceLanguage,
    onTranscript: (text) => setInputValue(text),
  });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || disabled || isTranscribing) return;
    const queryText = inputValue;
    setInputValue('');
    await onSend(queryText, toQueryLanguage(voiceLanguage));
  };

  return (
    <div className="input-area">
      {(isRecording || isTranscribing) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 14px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          {isTranscribing ? (
            <span>⏳ Cleaning up the transcript…</span>
          ) : (
            <>
              <span style={{ color: 'var(--accent-primary)' }}>{isPaused ? '⏸' : '●'}</span>
              <span>{isPaused ? 'Paused' : 'Listening…'}</span>
              <VoiceVisualizer analyser={getAnalyser()} isPaused={isPaused} />
              {canPause ? (
                <>
                  <button
                    type="button"
                    onClick={togglePause}
                    style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'transparent', border: '1px solid var(--glass-border)', borderRadius: '4px', padding: '2px 8px', fontSize: '12px', color: 'var(--text-secondary)', cursor: 'pointer' }}
                  >
                    {isPaused ? <Mic size={12} /> : <Pause size={12} />}
                    {isPaused ? 'Resume' : 'Pause'}
                  </button>
                  <span>— click the mic to stop and transcribe</span>
                </>
              ) : (
                <span>— speak, then click the mic when finished</span>
              )}
            </>
          )}
        </div>
      )}
      <form onSubmit={handleSubmit} className="input-box">
        <button type="button" className="action-btn" aria-label="Attach file">
          <Paperclip size={20} />
        </button>
        <input
          type="text"
          placeholder="Ask about cases, sections, or criminals..."
          value={inputValue}
          onChange={(e) => setInputValue(e.target.value)}
          disabled={disabled || isTranscribing}
        />
        <select
          value={voiceLanguage}
          onChange={(e) => setVoiceLanguage(e.target.value as IndicLanguageCode)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer', outline: 'none', marginRight: '2px', appearance: 'none' }}
          title="Voice input language"
        >
          {INDIC_LANGUAGES.map((l) => (
            <option key={l.code} value={l.code}>
              {l.code === 'mix-IN' ? 'MIX' : l.code.split('-')[0].toUpperCase()}
            </option>
          ))}
        </select>
        <button
          type="button"
          className="action-btn"
          aria-label={isRecording ? 'Stop recording' : 'Voice input'}
          onClick={toggleRecording}
          disabled={isTranscribing}
          style={isRecording ? { color: 'var(--accent-primary)', opacity: isPaused ? 0.5 : 1 } : {}}
        >
          <Mic size={20} />
        </button>
        <button
          type="submit"
          className="action-btn primary"
          disabled={!inputValue.trim() || disabled || isTranscribing}
          aria-label="Send message"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  );
}
