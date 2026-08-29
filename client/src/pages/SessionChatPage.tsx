import React, { useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Search, Mic, Pause, Paperclip, Send, Shield, Database } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { transcribe } from '../lib/api';
import { startWavRecording, type WavRecorder } from '../lib/wavRecorder';
import { VoiceVisualizer } from '../components/chat/VoiceVisualizer';
import { PIPELINE_STEPS, type Message, type QueryLanguage } from '../types/chat';
import { useAuthStore } from '../stores/authStore';
import { useChatStore } from '../stores/chatStore';
import { useEntityStore } from '../stores/entityStore';

// Phase 2: message state now lives in chatStore (keyed by :sessionId) so the SSE
// loop patches messages from outside the React tree. This component is a thin
// consumer -- Phase 3 splits it into ChatView / MessageList / MessageBubble /
// InputBar.

const EMPTY: Message[] = [];

export default function SessionChatPage() {
  const { caseId, sessionId } = useParams();
  const token = useAuthStore((s) => s.token);
  const displayName = useAuthStore((s) => s.displayName);
  const logout = useAuthStore((s) => s.logout);
  const openEntity = useEntityStore((s) => s.open);

  const messages = useChatStore((s) => (sessionId ? s.messagesBySession[sessionId] : undefined) ?? EMPTY);
  const isLoading = useChatStore((s) => (sessionId ? s.loadingBySession[sessionId] : false) ?? false);
  const feedbackStatus = useChatStore((s) => s.feedbackStatus);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const sendQuery = useChatStore((s) => s.sendQuery);
  const submitFeedback = useChatStore((s) => s.submitFeedback);

  const [inputValue, setInputValue] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState<QueryLanguage>('kn');

  const [activeCorrectionId, setActiveCorrectionId] = useState<string | null>(null);
  const [correctionExplanation, setCorrectionExplanation] = useState('');

  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const wavRecorderRef = useRef<WavRecorder | null>(null);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Load this session's history whenever the route id changes.
  useEffect(() => {
    if (!sessionId) return;
    loadHistory(sessionId);
  }, [sessionId, loadHistory]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading || isTranscribing || !sessionId) return;

    const queryText = inputValue;
    setInputValue('');
    await sendQuery({
      sessionId,
      caseId,
      text: queryText,
      language: voiceLanguage,
      token,
      onUnauthorized: logout,
    });
  };

  const handleFeedbackSubmit = async (
    item: NonNullable<Message['evidence']>[number],
    verdict: 'confirmed' | 'corrected',
    explanation?: string,
  ) => {
    const ok = await submitFeedback({
      sessionId,
      item,
      verdict,
      explanation,
      queryText: messages[messages.length - 2]?.content || '',
      officerId: displayName || 'officer',
    });
    if (ok) {
      setActiveCorrectionId(null);
      setCorrectionExplanation('');
    }
  };

  const handleMicClick = async () => {
    if (isRecording) {
      const recorder = wavRecorderRef.current;
      wavRecorderRef.current = null;
      setIsRecording(false);
      setIsPaused(false);
      if (!recorder) return;
      try {
        setIsTranscribing(true);
        const audioBlob = await recorder.stop();
        const { transcript } = await transcribe(audioBlob, voiceLanguage);
        setInputValue((prev) => (prev ? `${prev} ${transcript}` : transcript));
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

  const handleMicPauseToggle = () => {
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

  return (
    <div className="chat-container">
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`message ${msg.role}`}>
            <div className="message-avatar">
              {msg.role === 'assistant' ? (
                <Shield size={20} color="var(--accent-primary)" />
              ) : (
                <Search size={20} color="white" />
              )}
            </div>
            <div
              className="message-content-wrapper"
              style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '100%' }}
            >
              {msg.status && (
                <div className="w-full max-w-lg mb-4 mt-2">
                  <div className="flex items-center justify-between mb-2">
                    <div className="status-pill inline-flex items-center gap-2 py-1 px-3">
                      <div
                        className="pulse w-1.5 h-1.5 rounded-full animate-ping"
                        style={{ background: 'var(--accent-primary)' }}
                      />
                      <span className="uppercase font-medium text-[11px]">{msg.status}...</span>
                    </div>
                  </div>
                  <div className="flex items-center gap-1 w-full mt-3 px-1">
                    {PIPELINE_STEPS.map((step, idx) => {
                      const currentStepIdx = PIPELINE_STEPS.findIndex(
                        (s) => s.key === msg.status?.toLowerCase(),
                      );
                      const isCompleted = currentStepIdx > idx;
                      const isActive = msg.status?.toLowerCase() === step.key;
                      return (
                        <React.Fragment key={step.key}>
                          <div className="flex flex-col items-center flex-1 relative group">
                            <div
                              className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-semibold transition-all duration-300 border"
                              style={
                                isCompleted
                                  ? { background: 'var(--accent-primary)', borderColor: 'var(--accent-primary)', color: 'var(--bg-secondary)' }
                                  : isActive
                                    ? { background: 'var(--accent-glow)', borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' }
                                    : { background: 'var(--bg-tertiary)', borderColor: 'var(--glass-border)', color: 'var(--text-tertiary)' }
                              }
                            >
                              {isCompleted ? '✓' : idx + 1}
                            </div>
                            <span
                              className={`text-[8px] mt-1.5 hidden md:block whitespace-nowrap transition-colors ${isActive ? 'font-medium' : ''}`}
                              style={{ color: isActive ? 'var(--accent-primary)' : isCompleted ? 'var(--text-secondary)' : 'var(--text-tertiary)' }}
                            >
                              {step.label}
                            </span>
                          </div>
                          {idx < PIPELINE_STEPS.length - 1 && (
                            <div
                              className="h-0.5 flex-1 mx-0.5 rounded transition-all duration-300"
                              style={{ background: isCompleted ? 'var(--accent-primary)' : 'var(--glass-border)' }}
                            />
                          )}
                        </React.Fragment>
                      );
                    })}
                  </div>
                </div>
              )}

              <div className="message-content">
                {msg.content ? (
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                ) : msg.isStreaming ? (
                  <div className="flex flex-col gap-2 py-1">
                    <div className="flex items-center gap-1.5 mb-1">
                      <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-primary)', animationDelay: '0ms' }} />
                      <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-secondary)', animationDelay: '150ms' }} />
                      <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-gold)', animationDelay: '300ms' }} />
                    </div>
                    <div className="w-48 h-3 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
                    <div className="w-36 h-2.5 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
                  </div>
                ) : (
                  ''
                )}
              </div>

              {msg.evidence && msg.evidence.length > 0 && (
                <div className="evidence-card">
                  <details className="evidence-details group" style={{ width: '100%' }}>
                    <summary
                      className="evidence-summary cursor-pointer select-none list-none flex items-center justify-between"
                      style={{ borderBottom: 'none' }}
                    >
                      <div className="evidence-header flex items-center gap-2 text-sm">
                        <Database size={14} style={{ color: 'var(--accent-secondary)' }} />
                        <span>Retrieved Evidence ({msg.evidence.length} Citations)</span>
                      </div>
                      <span
                        className="text-xs group-open:rotate-180 transition-transform duration-200"
                        style={{ color: 'var(--text-tertiary)' }}
                      >
                        ▼
                      </span>
                    </summary>
                    <div className="evidence-content grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                      {msg.evidence.map((item, idx) => {
                        const confidenceTier = String(item.confidence ?? '').toLowerCase();
                        const confidenceColor =
                          confidenceTier === 'high'
                            ? 'text-emerald-800 bg-emerald-100 border-emerald-300'
                            : confidenceTier === 'medium'
                              ? 'text-amber-800 bg-amber-100 border-amber-300'
                              : 'text-rose-800 bg-rose-100 border-rose-300';
                        const openThis = () =>
                          openEntity({
                            type: 'fir',
                            id: item.fir_id ?? `evidence-${idx}`,
                            label: item.fir_id ?? 'Case File',
                            data: item.data ?? {},
                            evidenceItems: [item],
                          });
                        return (
                          <div
                            key={idx}
                            className="evidence-item p-3 rounded-sm flex flex-col gap-2 entity-clickable"
                            style={{ border: '1px solid var(--paper-line)', background: 'var(--bg-primary)', cursor: 'pointer' }}
                            onClick={openThis}
                            role="button"
                            tabIndex={0}
                            onKeyDown={(e) => {
                              if (e.key === 'Enter' || e.key === ' ') openThis();
                            }}
                            aria-label={`View details for ${item.data?.crime_no || item.fir_id || 'case'}`}
                          >
                            <div
                              className="flex items-center justify-between pb-2"
                              style={{ borderBottom: '1px dashed var(--paper-line)' }}
                            >
                              <div className="font-mono font-medium text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                                {item.data?.crime_no || item.fir_id || 'No Case ID'}
                              </div>
                              {item.confidence && (
                                <span
                                  className={`text-[10px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider font-semibold whitespace-nowrap ${confidenceColor}`}
                                >
                                  {item.confidence}
                                </span>
                              )}
                            </div>
                            <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                              {item.data?.crime_type && (
                                <div>
                                  <strong>Type:</strong> {item.data.crime_type}
                                </div>
                              )}
                              {item.data?.district && (
                                <div>
                                  <strong>District:</strong> {item.data.district}
                                </div>
                              )}
                              {item.data?.Date && (
                                <div>
                                  <strong>Date:</strong> {item.data.Date}
                                </div>
                              )}
                              {item.data?.weapon && (
                                <div>
                                  <strong>Weapon:</strong> {item.data.weapon}
                                </div>
                              )}
                              <div
                                className="text-[9px] mt-1"
                                style={{ color: 'var(--text-tertiary)', fontFamily: 'IBM Plex Mono, monospace' }}
                              >
                                Click to expand →
                              </div>
                            </div>

                            <div
                              className="feedback-controls mt-2 pt-2 border-t"
                              style={{ borderColor: 'var(--glass-border)' }}
                              onClick={(e) => e.stopPropagation()}
                            >
                              {feedbackStatus[item.edge_id || item.fir_id] ? (
                                <div className="text-[10px] text-emerald-700 font-medium flex items-center gap-1">
                                  <span>✓</span> Feedback recorded ({feedbackStatus[item.edge_id || item.fir_id].verdict})
                                </div>
                              ) : (
                                <div className="flex flex-col gap-2">
                                  {activeCorrectionId === (item.edge_id || item.fir_id) ? (
                                    <div className="flex flex-col gap-2 mt-1">
                                      <textarea
                                        className="w-full text-xs p-1.5 rounded"
                                        style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)', outline: 'none' }}
                                        placeholder="Explain the correction (required)..."
                                        value={correctionExplanation}
                                        onChange={(e) => setCorrectionExplanation(e.target.value)}
                                        rows={2}
                                        required
                                      />
                                      <div className="flex gap-2 justify-end">
                                        <button
                                          type="button"
                                          onClick={() => setActiveCorrectionId(null)}
                                          className="px-2 py-1 text-[10px] rounded border"
                                          style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', borderColor: 'var(--glass-border)', cursor: 'pointer' }}
                                        >
                                          Cancel
                                        </button>
                                        <button
                                          type="button"
                                          disabled={!correctionExplanation.trim()}
                                          onClick={() => handleFeedbackSubmit(item, 'corrected', correctionExplanation)}
                                          className="px-2 py-1 text-[10px] rounded text-white"
                                          style={{ background: correctionExplanation.trim() ? 'var(--accent-primary)' : 'var(--text-tertiary)', cursor: correctionExplanation.trim() ? 'pointer' : 'not-allowed' }}
                                        >
                                          Submit
                                        </button>
                                      </div>
                                    </div>
                                  ) : (
                                    <div className="flex items-center gap-2">
                                      <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                                        Was this connection useful?
                                      </span>
                                      <button
                                        type="button"
                                        className="px-2 py-0.5 text-[10px] rounded border"
                                        style={{ borderColor: 'rgba(47, 74, 60, 0.5)', color: 'var(--accent-secondary)', cursor: 'pointer', background: 'transparent' }}
                                        onClick={() => handleFeedbackSubmit(item, 'confirmed')}
                                      >
                                        ✓ Confirm
                                      </button>
                                      <button
                                        type="button"
                                        className="px-2 py-0.5 text-[10px] rounded border"
                                        style={{ borderColor: 'rgba(138, 42, 36, 0.5)', color: 'var(--accent-primary)', cursor: 'pointer', background: 'transparent' }}
                                        onClick={() => {
                                          setActiveCorrectionId(item.edge_id || item.fir_id);
                                          setCorrectionExplanation('');
                                        }}
                                      >
                                        ✗ Correct
                                      </button>
                                    </div>
                                  )}
                                </div>
                              )}
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </details>
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="input-area">
        {(isRecording || isTranscribing) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '6px 14px', fontSize: '13px', color: 'var(--text-secondary)' }}>
            {isTranscribing ? (
              <span>⏳ Transcribing your audio...</span>
            ) : (
              <>
                <span style={{ color: 'var(--accent-primary)' }}>{isPaused ? '⏸' : '●'}</span>
                <span>{isPaused ? 'Recording paused' : 'Recording...'}</span>
                <VoiceVisualizer analyser={wavRecorderRef.current?.getAnalyser() || null} isPaused={isPaused} />
                <button
                  type="button"
                  onClick={handleMicPauseToggle}
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
            disabled={isLoading || isTranscribing}
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
            onClick={handleMicClick}
            disabled={isTranscribing}
            style={isRecording ? { color: 'var(--accent-primary)', opacity: isPaused ? 0.5 : 1 } : {}}
          >
            <Mic size={20} />
          </button>
          <button
            type="submit"
            className="action-btn primary"
            disabled={!inputValue.trim() || isLoading || isTranscribing}
            aria-label="Send message"
          >
            <Send size={18} />
          </button>
        </form>
      </div>
    </div>
  );
}
