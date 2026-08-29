import React, { useState } from 'react';
import { Mic, Pause, Paperclip, Send } from 'lucide-react';
import { VoiceVisualizer } from './VoiceVisualizer';
import { useVoiceRecorder } from '../../hooks/useVoiceRecorder';
import type { QueryLanguage } from '../../types/chat';

// Phase 3: the composer -- text field, voice-input language select, mic + send,
// and the recording status strip. Extracted verbatim from SessionChatPage
// (originally App.tsx input area). Owns its own draft + language state; the mic
// flow lives in useVoiceRecorder.

interface InputBarProps {
  disabled: boolean;
  onSend: (text: string, language: QueryLanguage) => void | Promise<void>;
}

export function InputBar({ disabled, onSend }: InputBarProps) {
  const [inputValue, setInputValue] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState<QueryLanguage>('kn');

  const { isRecording, isPaused, isTranscribing, toggleRecording, togglePause, getAnalyser } =
    useVoiceRecorder({
      language: voiceLanguage,
      onTranscript: (transcript) =>
        setInputValue((prev) => (prev ? `${prev} ${transcript}` : transcript)),
    });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || disabled || isTranscribing) return;
    const queryText = inputValue;
    setInputValue('');
    await onSend(queryText, voiceLanguage);
  };

  return (
    <div className="input-area">
      {(isRecording || isTranscribing) && (
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 14px', fontSize: '13px', color: 'var(--text-secondary)' }}>
          {isTranscribing ? (
            <span>⏳ Transcribing your audio...</span>
          ) : (
            <>
              <span style={{ color: 'var(--accent-primary)' }}>{isPaused ? '⏸' : '●'}</span>
              <span>{isPaused ? 'Recording paused' : 'Recording...'}</span>
              <VoiceVisualizer analyser={getAnalyser()} isPaused={isPaused} />
              <button
                type="button"
                onClick={togglePause}
                style={{ display: 'flex', alignItems: 'center', gap: '4px', background: 'transparent', border: '1px solid var(--glass-border)', borderRadius: '4px', padding: '2px 8px', fontSize: '12px', color: 'var(--text-secondary)', cursor: 'pointer' }}
              >
                {isPaused ? <Mic size={12} /> : <Pause size={12} />}
                {isPaused ? 'Resume' : 'Pause'}
              </button>
              <span>— click the mic icon to stop and transcribe</span>
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
          onChange={(e) => setVoiceLanguage(e.target.value as QueryLanguage)}
          style={{ background: 'transparent', border: 'none', color: 'var(--text-secondary)', fontSize: '12px', fontWeight: 'bold', cursor: 'pointer', outline: 'none', marginRight: '2px', appearance: 'none' }}
          title="Voice Input Language"
        >
          <option value="en">EN</option>
          <option value="hi">HI</option>
          <option value="kn">KN</option>
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
