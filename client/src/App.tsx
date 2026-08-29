import React, { useState, useRef, useEffect } from 'react';
import { Search, Mic, Pause, Paperclip, Send, Shield, Database, LayoutDashboard, Settings, LogOut, Trash2 } from 'lucide-react';
import DashboardPanel from './components/dashboard/DashboardPanel';
import Login from './components/Login';
import EntityDrawer from './components/dashboard/EntityDrawer';
import { useEntityDrawer } from './hooks/useEntityDrawer';
import ReactMarkdown from 'react-markdown';
import { fetchWithRetry } from './lib/utils';
import { streamQuery } from './lib/sse';
import { pollForCompletedJob } from './lib/pollJob';
import { startWavRecording, type WavRecorder } from './lib/wavRecorder';
import { VoiceVisualizer } from './components/chat/VoiceVisualizer';
import { PIPELINE_STEPS, type Message } from './types/chat';

export default function App() {
  const [authToken, setAuthToken] = useState<string | null>(() => sessionStorage.getItem("ps1_auth_token"));
  const [displayName, setDisplayName] = useState<string>(() => sessionStorage.getItem("ps1_display_name") ?? '');

  const handleLogin = (token: string, _username: string, _role: string, name: string) => {
    sessionStorage.setItem("ps1_auth_token", token);
    sessionStorage.setItem("ps1_display_name", name);
    setAuthToken(token);
    setDisplayName(name);
  };

  const handleLogout = () => {
    sessionStorage.removeItem("ps1_auth_token");
    sessionStorage.removeItem("ps1_display_name");
    setAuthToken(null);
    setDisplayName('');
  };

  const defaultMessages: Message[] = [{
    id: '1',
    role: 'assistant',
    content: 'Greetings Officer. I am the PS-1 Conversational Intelligence System. How can I assist you today?'
  }];
  const [sessionsMessages, setSessionsMessages] = useState<Record<string, Message[]>>({});
  
  const updateSessionMessages = (sessionId: string, updater: (prev: Message[]) => Message[]) => {
    setSessionsMessages(prev => {
      const current = prev[sessionId] || defaultMessages;
      return { ...prev, [sessionId]: updater(current) };
    });
  };
  const [inputValue, setInputValue] = useState('');
  const [voiceLanguage, setVoiceLanguage] = useState('kn');
  const [isLoading, setIsLoading] = useState(false);
  const [isCreatingCase, setIsCreatingCase] = useState(false);
  const [isCreatingSession, setIsCreatingSession] = useState(false);
  const [activeView, setActiveView] = useState<'query' | 'dashboard'>('query');

  const [cases, setCases] = useState<any[]>([]);
  const [activeCaseId, setActiveCaseId] = useState<string | null>(null);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const messages = activeSessionId && sessionsMessages[activeSessionId] ? sessionsMessages[activeSessionId] : defaultMessages;
  const [caseSessions, setCaseSessions] = useState<Record<string, any[]>>({});
  
  const fetchCases = async (currentActiveCaseId?: string | null) => {
    if (!authToken) return;
    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/cases`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCases(data.cases || []);
        if (data.cases && data.cases.length > 0) {
          const firstCaseId = data.cases[0].case_id;
          // Auto-expand if nothing is active
          if (!currentActiveCaseId && !activeCaseId) {
             setActiveCaseId(firstCaseId);
             fetchSessions(firstCaseId);
          }
        }
      }
    } catch(e) { console.error("Error fetching cases", e); }
  };

  const fetchSessions = async (caseId: string) => {
    if (!authToken) return;
    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/cases/${caseId}/sessions`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        setCaseSessions(prev => ({ ...prev, [caseId]: data.sessions || [] }));
      }
    } catch(e) { console.error("Error fetching sessions", e); }
  };

  const deleteCase = async (caseId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this case? This action cannot be undone.")) return;
    
    // Optimistic update
    setCases(prev => prev.filter(c => c.case_id !== caseId));
    if (activeCaseId === caseId) setActiveCaseId(null);

    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/cases/${caseId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error("Delete case failed");
    } catch(err) { 
      console.error("Error deleting case", err); 
      fetchCases(); // Revert on failure
    }
  };

  const deleteSession = async (caseId: string, sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm("Are you sure you want to delete this session?")) return;
    
    // Optimistic update
    setCaseSessions(prev => ({
      ...prev,
      [caseId]: prev[caseId]?.filter(s => s.session_id !== sessionId) || []
    }));
    if (activeSessionId === sessionId) setActiveSessionId(null);

    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/sessions/${sessionId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (!res.ok) throw new Error("Delete session failed");
    } catch(err) { 
      console.error("Error deleting session", err); 
      fetchSessions(caseId); // Revert on failure
    }
  };

  const createCase = async () => {
    if (isCreatingCase) return;
    const title = prompt("Enter Case Title:");
    if (!title) return;
    setIsCreatingCase(true);
    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/cases`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({ title, crime_no: null, district: null })
      });
      if (res.ok) {
        const newCase = await res.json();
        setCases(prev => [newCase, ...prev]);
        setActiveCaseId(newCase.case_id);
        await createSession(newCase.case_id);
      }
    } catch(e) { console.error("Error creating case", e); }
    finally { setIsCreatingCase(false); }
  };

  const createSession = async (caseId: string) => {
    if (isCreatingSession) return;
    setIsCreatingSession(true);
    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/cases/${caseId}/sessions`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const newSession = await res.json();
        setActiveSessionId(newSession.session_id);
        updateSessionMessages(newSession.session_id, () => [{ id: '1', role: 'assistant', content: 'New session started. How can I assist?' }]);
        fetchSessions(caseId);
      }
    } catch(e) { console.error("Error creating session", e); }
    finally { setIsCreatingSession(false); }
  };

  const loadSession = async (sessionId: string) => {
    setActiveSessionId(sessionId);
    try {
      const res = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/sessions/${sessionId}`, {
        headers: { Authorization: `Bearer ${authToken}` }
      });
      if (res.ok) {
        const data = await res.json();
        const historyArray = data.history || [];
        updateSessionMessages(sessionId, () => {
          if (historyArray.length === 0) {
            return [{ id: '1', role: 'assistant', content: 'New session started. How can I assist?' }];
          }
          return [
            { id: '1', role: 'assistant', content: `Restored session history.` },
            ...historyArray.flatMap((h: any, idx: number) => [
              {
                id: `hist-${idx}-u`,
                role: 'user',
                content: h.q
              },
              {
                id: `hist-${idx}-a`,
                role: 'assistant',
                content: h.a,
                evidence: h.evidence,
                visualization: h.visualization
              }
            ])
          ];
        });
      }
    } catch(e) { console.error("Error loading session", e); }
  };

  useEffect(() => {
    fetchCases();
  }, [authToken]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { selectedEntity, openEntity, closeDrawer } = useEntityDrawer();

  // Reasoning Feedback Loop state hooks
  const [feedbackStatus, setFeedbackStatus] = useState<Record<string, { verdict: 'confirmed' | 'corrected' }>>({});
  const [activeCorrectionId, setActiveCorrectionId] = useState<string | null>(null);
  const [correctionExplanation, setCorrectionExplanation] = useState<string>('');

  const handleFeedbackSubmit = async (item: any, verdict: 'confirmed' | 'corrected', explanation?: string) => {
    const key = item.edge_id || item.fir_id;
    try {
      const response = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/feedback/correction`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          event_id: crypto.randomUUID(),
          session_id: activeSessionId,
          officer_id: displayName || 'officer',
          timestamp: new Date().toISOString(),
          query_text: messages[messages.length - 2]?.content || '',
          edge_type: item.edge_type || 'NARRATIVE_SIMILARITY',
          crime_type: item.crime_type || null,
          edge_id: item.edge_id || null,
          verdict,
          explanation: explanation || null
        })
      });
      if (!response.ok) throw new Error('Failed to submit feedback');
      setFeedbackStatus(prev => ({ ...prev, [key]: { verdict } }));
      setActiveCorrectionId(null);
      setCorrectionExplanation('');
    } catch (err) {
      console.error(err);
      alert('Error submitting feedback');
    }
  };

  const [isRecording, setIsRecording] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  // BUG FIX: this used MediaRecorder, which emits webm/opus in Chrome. Zia
  // ASR rejects .webm outright (400 INVALID_FILE_EXTENSION), so every voice
  // query failed. startWavRecording() captures PCM and encodes WAV instead.
  const wavRecorderRef = useRef<WavRecorder | null>(null);

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
        const formData = new FormData();
        formData.append('audio', audioBlob, 'recording.wav');
        formData.append('language', voiceLanguage);

        const response = await fetchWithRetry(`${import.meta.env.VITE_API_BASE_URL || ''}/api/transcribe`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${authToken}`
          },
          body: formData
        });

        if (response.ok) {
          const data = await response.json();
          setInputValue(prev => prev ? `${prev} ${data.transcript}` : data.transcript);
        } else {
          console.error('Transcription failed:', await response.text());
          alert('Voice transcription failed. Please try again or type your query.');
        }
      } catch (err) {
        console.error('Error sending audio:', err);
        alert('Voice transcription failed. Please try again or type your query.');
      } finally {
        setIsTranscribing(false);
      }
    } else {
      try {
        wavRecorderRef.current = await startWavRecording();
        setIsRecording(true);
        setIsPaused(false);
      } catch (err) {
        console.error('Error accessing microphone:', err);
        alert('Could not access microphone.');
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



  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // Keeps the pipeline Function's container warm. A cold start adds ~11s to
  // the first query, which is both a bad first impression and enough to push
  // a slow query past the window AppSail holds the SSE response open.
  // Deliberately invisible: fire-and-forget, no state, no UI, and failures are
  // swallowed -- pre-warming is an optimisation and must never surface to the
  // officer or block anything.
  useEffect(() => {
    if (!authToken) return;
    const ping = () => {
      fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/warmup`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      }).catch(() => { /* best-effort only */ });
    };
    ping();                                   // warm immediately on sign-in
    const id = setInterval(ping, 4 * 60_000); // and keep it warm while in use
    return () => clearInterval(id);
  }, [authToken]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading || isTranscribing) return;
    if (!activeSessionId) {
      alert('Please select or create a case session first.');
      return;
    }

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: inputValue
    };

    const targetSessionId = activeSessionId;
    updateSessionMessages(targetSessionId, prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    const assistantMsgId = crypto.randomUUID();
    updateSessionMessages(targetSessionId, prev => [...prev, {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      status: 'dispatching_job',
      isStreaming: true
    }]);

    // Patch just this assistant message. Reducer bodies are unchanged from the
    // old inline SSE handler — only the frame parsing/streaming moved to lib/sse.ts.
    const patch = (fn: (msg: Message) => Message) =>
      updateSessionMessages(targetSessionId, prev => prev.map(msg => (msg.id === assistantMsgId ? fn(msg) : msg)));

    try {
      const { jobId, sawTerminalEvent } = await streamQuery(
        { sessionId: activeSessionId, query: userMessage.content, language: voiceLanguage, token: authToken },
        {
          onUnauthorized: handleLogout,
          onProgress: status => patch(msg => ({ ...msg, status })),
          onEvidence: evidence => patch(msg => ({ ...msg, evidence })),
          onVisualization: visualization => patch(msg => ({ ...msg, visualization })),
          onToken: token => patch(msg => ({ ...msg, content: token, isStreaming: false, status: undefined })),
          onDone: () => patch(msg => ({ ...msg, isStreaming: false, status: undefined })),
          onError: message => patch(msg => ({ ...msg, content: `Error: ${message}`, isStreaming: false, status: undefined })),
        },
      );

      // BUG FIX: AppSail closes the SSE response after ~45s. A pipeline that
      // needs longer (cold Function start plus a slow synthesis) therefore had
      // its stream cut with no "done" and no "error", leaving this message
      // stuck on its last progress stage forever -- even though the pipeline
      // finished and wrote its answer to NoSQL. If the stream ended without a
      // terminal event, poll for the finished job instead of giving up.
      if (!sawTerminalEvent && jobId) {
        const recovered = await pollForCompletedJob(jobId, authToken);
        patch(msg =>
          recovered?.status === 'done'
            ? {
                ...msg,
                content: recovered.answer ?? msg.content,
                evidence: recovered.evidence ?? msg.evidence,
                visualization: recovered.visualization ?? msg.visualization,
                isStreaming: false,
                status: undefined,
              }
            : {
                ...msg,
                content:
                  recovered?.error ??
                  'This query took longer than expected and the connection closed. Please try again.',
                isStreaming: false,
                status: undefined,
              },
        );
      }

    } catch (error) {
      console.error(error);
      // BUG FIX: this previously said "Make sure the backend server is
      // running on port 8000" unconditionally -- a local-dev-only assumption
      // that's actively wrong and confusing on the deployed instance, where
      // there's no localhost backend for an officer to check.
      const message = error instanceof TypeError
        ? "Unable to reach the server. Please check your connection and try again."
        : "Something went wrong while processing your query. Please try again.";
      updateSessionMessages(targetSessionId, prev => prev.map(msg =>
        msg.id === assistantMsgId ? { ...msg, content: message, isStreaming: false, status: undefined } : msg
      ));
    } finally {
      setIsLoading(false);
    }
  };

  if (!authToken) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <>
      <div className="ambient-bg" />
      <div className="app-container">
        {/* Sidebar */}
        <aside className="sidebar" aria-label="System Navigation">
          <header className="brand">
            <div className="brand-icon">
              <Shield color="var(--accent-primary)" size={20} />
            </div>
            <h1>PS-1 <span>CIS</span></h1>
          </header>

          <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }} aria-label="Main Navigation">

            <div style={{ padding: '0 12px 12px 12px', borderBottom: '1px solid var(--paper-line)', marginBottom: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
                <span style={{ fontSize: '12px', color: 'var(--text-secondary)', fontWeight: 600, textTransform: 'uppercase' }}>Cases</span>
                <button onClick={createCase} disabled={isCreatingCase} style={{ background: 'transparent', border: 'none', color: isCreatingCase ? 'var(--text-tertiary)' : 'var(--accent-primary)', cursor: isCreatingCase ? 'not-allowed' : 'pointer', fontSize: '18px' }}>+</button>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', maxHeight: '30vh', overflowY: 'auto' }}>
                {cases.map(c => (
                  <div key={c.case_id}>
                    <div 
                      onClick={() => { setActiveCaseId(c.case_id); fetchSessions(c.case_id); }}
                      style={{ 
                        padding: '6px 8px', 
                        fontSize: '13px', 
                        cursor: 'pointer',
                        borderRadius: '4px',
                        background: activeCaseId === c.case_id ? 'var(--sidebar-accent)' : 'transparent',
                        color: activeCaseId === c.case_id ? 'var(--text-primary)' : 'var(--text-secondary)',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}
                    >
                      <span className="truncate">{c.title}</span>
                      <button 
                        onClick={(e) => deleteCase(c.case_id, e)} 
                        className="opacity-50 hover:opacity-100 hover:text-red-500 transition-opacity" 
                        style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}
                        title="Delete Case"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                    {activeCaseId === c.case_id && (
                      <div style={{ paddingLeft: '12px', borderLeft: '1px dashed var(--paper-line)', marginLeft: '8px', marginTop: '4px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
                        <button onClick={() => createSession(c.case_id)} disabled={isCreatingSession} style={{ textAlign: 'left', background: 'transparent', border: 'none', color: isCreatingSession ? 'var(--text-tertiary)' : 'var(--accent-secondary)', fontSize: '11px', cursor: isCreatingSession ? 'not-allowed' : 'pointer' }}>{isCreatingSession ? 'Creating...' : '+ New Session'}</button>
                        {(caseSessions[c.case_id] || []).map(s => (
                          <div 
                            key={s.session_id} 
                            onClick={() => loadSession(s.session_id)}
                            style={{ 
                              fontSize: '11px', 
                              cursor: 'pointer',
                              padding: '2px 4px',
                              borderRadius: '2px',
                              background: activeSessionId === s.session_id ? 'var(--bg-tertiary)' : 'transparent',
                              color: activeSessionId === s.session_id ? 'var(--accent-primary)' : 'var(--text-tertiary)',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center'
                            }}
                          >
                            <span className="truncate">{s.title || "New Session..."}</span>
                            <button 
                              onClick={(e) => deleteSession(c.case_id, s.session_id, e)} 
                              className="opacity-50 hover:opacity-100 hover:text-red-500 transition-opacity" 
                              style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '2px' }}
                              title="Delete Session"
                            >
                              <Trash2 size={10} />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <button
              type="button"
              onClick={() => setActiveView('query')}
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                padding: '12px',
                borderRadius: '12px',
                background: activeView === 'query' ? 'var(--sidebar-accent)' : 'transparent',
                color: activeView === 'query' ? 'var(--text-primary)' : 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer'
              }}
              aria-current={activeView === 'query' ? 'page' : undefined}
            >
              <Search size={18} /> Active Query
            </button>
            <button
              type="button"
              onClick={() => setActiveView('dashboard')}
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                padding: '12px',
                borderRadius: '12px',
                background: activeView === 'dashboard' ? 'var(--sidebar-accent)' : 'transparent',
                color: activeView === 'dashboard' ? 'var(--text-primary)' : 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer'
              }}
              aria-current={activeView === 'dashboard' ? 'page' : undefined}
            >
              <LayoutDashboard size={18} /> Dashboard
            </button>
            <button
              type="button"
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                padding: '12px',
                borderRadius: '12px',
                background: 'transparent',
                color: 'var(--text-tertiary)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'not-allowed'
              }}
              disabled
            >
              <Database size={18} /> Data Store
            </button>
          </nav>

          <footer style={{ marginTop: 'auto' }}>
            {displayName && (
              <div style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Signed in as <strong style={{ color: 'var(--text-primary)' }}>{displayName}</strong>
              </div>
            )}
            <button
              type="button"
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                padding: '12px',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                background: 'transparent'
              }}
              aria-label="Settings"
            >
              <Settings size={18} /> Settings
            </button>
            <button
              type="button"
              onClick={handleLogout}
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                padding: '12px',
                color: 'var(--text-secondary)',
                display: 'flex',
                alignItems: 'center',
                gap: '12px',
                cursor: 'pointer',
                background: 'transparent'
              }}
              aria-label="Sign Out"
            >
              <LogOut size={18} /> Sign Out
            </button>
          </footer>
        </aside>

        {/* Main Content Area */}
        <main className="chat-container">
          {activeView === 'query' ? (
            <>
              <div className="chat-messages">
                {messages.map(msg => (
                  <div key={msg.id} className={`message ${msg.role}`}>
                    <div className="message-avatar">
                      {msg.role === 'assistant' ? <Shield size={20} color="var(--accent-primary)" /> : <Search size={20} color="white" />}
                    </div>
                    <div className="message-content-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '100%' }}>
                      
                      {msg.status && (
                        <div className="w-full max-w-lg mb-4 mt-2">
                          <div className="flex items-center justify-between mb-2">
                            <div className="status-pill inline-flex items-center gap-2 py-1 px-3">
                              <div className="pulse w-1.5 h-1.5 rounded-full animate-ping" style={{ background: 'var(--accent-primary)' }} />
                              <span className="uppercase font-medium text-[11px]">{msg.status}...</span>
                            </div>
                          </div>
                          <div className="flex items-center gap-1 w-full mt-3 px-1">
                            {PIPELINE_STEPS.map((step, idx) => {
                              const currentStepIdx = PIPELINE_STEPS.findIndex(s => s.key === msg.status?.toLowerCase());
                              const isCompleted = currentStepIdx > idx;
                              const isActive = msg.status?.toLowerCase() === step.key;
                              
                              return (
                                <React.Fragment key={step.key}>
                                  <div className="flex flex-col items-center flex-1 relative group">
                                    <div 
                                      className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-semibold transition-all duration-300 border"
                                      style={
                                        isCompleted ? { background: 'var(--accent-primary)', borderColor: 'var(--accent-primary)', color: 'var(--bg-secondary)' } :
                                        isActive ? { background: 'var(--accent-glow)', borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' } :
                                        { background: 'var(--bg-tertiary)', borderColor: 'var(--glass-border)', color: 'var(--text-tertiary)' }
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
                        ) : (msg.isStreaming ? (
                          <div className="flex flex-col gap-2 py-1">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-primary)', animationDelay: '0ms' }} />
                              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-secondary)', animationDelay: '150ms' }} />
                              <span className="w-2 h-2 rounded-full animate-bounce" style={{ background: 'var(--accent-gold)', animationDelay: '300ms' }} />
                            </div>
                            <div className="w-48 h-3 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
                            <div className="w-36 h-2.5 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
                          </div>
                        ) : '')}
                      </div>
                      
                      {msg.evidence && msg.evidence.length > 0 && (
                        <div className="evidence-card">
                          <details className="evidence-details group" style={{ width: '100%' }}>
                            <summary className="evidence-summary cursor-pointer select-none list-none flex items-center justify-between" style={{ borderBottom: 'none' }}>
                              <div className="evidence-header flex items-center gap-2 text-sm">
                                <Database size={14} style={{ color: 'var(--accent-secondary)' }} />
                                <span>Retrieved Evidence ({msg.evidence.length} Citations)</span>
                              </div>
                              <span className="text-xs group-open:rotate-180 transition-transform duration-200" style={{ color: 'var(--text-tertiary)' }}>▼</span>
                            </summary>
                            <div className="evidence-content grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                              {msg.evidence.map((item, idx) => {
                                const confidenceTier = String(item.confidence ?? '').toLowerCase();
                                const confidenceColor =
                                  confidenceTier === 'high' ? 'text-emerald-800 bg-emerald-100 border-emerald-300' :
                                  confidenceTier === 'medium' ? 'text-amber-800 bg-amber-100 border-amber-300' :
                                  'text-rose-800 bg-rose-100 border-rose-300';
                                return (
                                  <div
                                    key={idx}
                                    className="evidence-item p-3 rounded-sm flex flex-col gap-2 entity-clickable"
                                    style={{ border: '1px solid var(--paper-line)', background: 'var(--bg-primary)', cursor: 'pointer' }}
                                    onClick={() => openEntity({
                                      type: 'fir',
                                      id: item.fir_id ?? `evidence-${idx}`,
                                      label: item.fir_id ?? 'Case File',
                                      data: item.data ?? {},
                                      evidenceItems: [item],
                                    })}
                                    role="button"
                                    tabIndex={0}
                                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') openEntity({ type: 'fir', id: item.fir_id ?? `evidence-${idx}`, label: item.fir_id ?? 'Case File', data: item.data ?? {}, evidenceItems: [item] }); }}
                                    aria-label={`View details for ${item.data?.crime_no || item.fir_id || 'case'}`}
                                  >
                                    <div className="flex items-center justify-between pb-2" style={{ borderBottom: '1px dashed var(--paper-line)' }}>
                                      <div className="font-mono font-medium text-sm truncate" style={{ color: 'var(--text-primary)' }}>
                                        {item.data?.crime_no || item.fir_id || "No Case ID"}
                                      </div>
                                      {item.confidence && (
                                        <span className={`text-[10px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider font-semibold whitespace-nowrap ${confidenceColor}`}>
                                          {item.confidence}
                                        </span>
                                      )}
                                    </div>
                                    <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
                                      {item.data?.crime_type && <div><strong>Type:</strong> {item.data.crime_type}</div>}
                                      {item.data?.district && <div><strong>District:</strong> {item.data.district}</div>}
                                      {item.data?.Date && <div><strong>Date:</strong> {item.data.Date}</div>}
                                      {item.data?.weapon && <div><strong>Weapon:</strong> {item.data.weapon}</div>}
                                      <div className="text-[9px] mt-1" style={{ color: 'var(--text-tertiary)', fontFamily: 'IBM Plex Mono, monospace' }}>Click to expand →</div>
                                    </div>

                                    {/* Feedback section */}
                                    <div 
                                      className="feedback-controls mt-2 pt-2 border-t"
                                      style={{ borderColor: 'var(--glass-border)' }}
                                      onClick={(e) => e.stopPropagation()}
                                    >
                                      {feedbackStatus[item.edge_id || item.fir_id] ? (
                                        <div className="text-[10px] text-emerald-400 font-medium flex items-center gap-1">
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
                                              <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>Was this connection useful?</span>
                                              <button
                                                type="button"
                                                className="px-2 py-0.5 text-[10px] rounded border hover:bg-emerald-950/20"
                                                style={{ borderColor: 'rgba(16, 185, 129, 0.4)', color: '#10b981', cursor: 'pointer', background: 'transparent' }}
                                                onClick={() => handleFeedbackSubmit(item, 'confirmed')}
                                              >
                                                ✓ Confirm
                                              </button>
                                              <button
                                                type="button"
                                                className="px-2 py-0.5 text-[10px] rounded border hover:bg-rose-950/20"
                                                style={{ borderColor: 'rgba(239, 68, 68, 0.4)', color: '#ef4444', cursor: 'pointer', background: 'transparent' }}
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
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    padding: '6px 14px',
                    fontSize: '13px',
                    color: 'var(--text-secondary)',
                  }}>
                    {isTranscribing ? (
                      <span>⏳ Transcribing your audio...</span>
                    ) : (
                      <>
                        <span style={{ color: '#dc2626' }}>{isPaused ? '⏸' : '●'}</span>
                        <span>{isPaused ? 'Recording paused' : 'Recording...'}</span>
                        <VoiceVisualizer analyser={wavRecorderRef.current?.getAnalyser() || null} isPaused={isPaused} />
                        <button
                          type="button"
                          onClick={handleMicPauseToggle}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '4px',
                            background: 'transparent',
                            border: '1px solid var(--glass-border)',
                            borderRadius: '4px',
                            padding: '2px 8px',
                            fontSize: '12px',
                            color: 'var(--text-secondary)',
                            cursor: 'pointer',
                          }}
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
                    onChange={e => setInputValue(e.target.value)}
                    disabled={isLoading || isTranscribing}
                  />
                  <select
                    value={voiceLanguage}
                    onChange={(e) => setVoiceLanguage(e.target.value)}
                    style={{
                      background: 'transparent',
                      border: 'none',
                      color: 'var(--text-secondary)',
                      fontSize: '12px',
                      fontWeight: 'bold',
                      cursor: 'pointer',
                      outline: 'none',
                      marginRight: '2px',
                      appearance: 'none'
                    }}
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
                    style={isRecording ? { color: '#dc2626', opacity: isPaused ? 0.5 : 1 } : {}}
                  >
                    <Mic size={20} />
                  </button>
                  <button type="submit" className="action-btn primary" disabled={!inputValue.trim() || isLoading || isTranscribing} aria-label="Send message">
                    <Send size={18} />
                  </button>
                </form>
              </div>
            </>
          ) : (
            <DashboardPanel 
              visualization={messages.filter(m => m.role === 'assistant').pop()?.visualization} 
              evidence={messages.filter(m => m.role === 'assistant').pop()?.evidence}
            />
          )}
        </main>
      </div>
      {/* App-level entity drawer — works from both query and dashboard views */}
      <EntityDrawer entity={selectedEntity} onClose={closeDrawer} />
    </>
  );
}