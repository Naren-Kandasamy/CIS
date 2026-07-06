import React, { useState, useRef, useEffect } from 'react';
import { Search, Mic, Paperclip, Send, Shield, Database, LayoutDashboard, Settings, LogOut } from 'lucide-react';
import DashboardPanel from './components/dashboard/DashboardPanel';
import Login from './components/Login';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  evidence?: any[];
  visualization?: any;
  status?: string;
  isStreaming?: boolean;
}

const SESSION_ID = sessionStorage.getItem("ps1_session_id") ?? (() => {
  const id = crypto.randomUUID();
  sessionStorage.setItem("ps1_session_id", id);
  return id;
})();

const PIPELINE_STEPS = [
  { key: 'understanding query', label: 'NER & Intent' },
  { key: 'resolving entities', label: 'Entity Match' },
  { key: 'planning execution', label: 'DAG Planner' },
  { key: 'retrieving evidence', label: 'Retrieval' },
  { key: 'confidence scoring', label: 'Confidence' },
  { key: 'building visualization', label: 'Visualizer' },
  { key: 'synthesizing response', label: 'Synthesis' }
];

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

  const [messages, setMessages] = useState<Message[]>([
    {
      id: '1',
      role: 'assistant',
      content: 'Greetings Officer. I am the PS-1 Conversational Intelligence System. How can I assist you today?'
    }
  ]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [activeView, setActiveView] = useState<'query' | 'dashboard'>('query');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const [isRecording, setIsRecording] = useState(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<BlobPart[]>([]);

  const handleMicClick = async () => {
    if (isRecording) {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
        mediaRecorderRef.current.stop();
      }
      setIsRecording(false);
    } else {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        const mediaRecorder = new MediaRecorder(stream);
        mediaRecorderRef.current = mediaRecorder;
        audioChunksRef.current = [];

        mediaRecorder.ondataavailable = (e) => {
          if (e.data.size > 0) {
            audioChunksRef.current.push(e.data);
          }
        };

        mediaRecorder.onstop = async () => {
          const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
          const formData = new FormData();
          formData.append('audio', audioBlob, 'recording.webm');
          formData.append('language', 'kn'); // Default to Kannada for PS-1

          try {
            setIsLoading(true);
            const response = await fetch('/api/transcribe', {
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
            }
          } catch (err) {
            console.error('Error sending audio:', err);
          } finally {
            setIsLoading(false);
          }
          
          stream.getTracks().forEach(track => track.stop());
        };

        mediaRecorder.start();
        setIsRecording(true);
      } catch (err) {
        console.error('Error accessing microphone:', err);
        alert('Could not access microphone.');
      }
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputValue.trim() || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: inputValue
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    const assistantMsgId = crypto.randomUUID();
    setMessages(prev => [...prev, {
      id: assistantMsgId,
      role: 'assistant',
      content: '',
      status: 'dispatching_job',
      isStreaming: true
    }]);

    try {
      const response = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/query`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${authToken}`
        },
        body: JSON.stringify({
          session_id: SESSION_ID,
          query: userMessage.content
        })
      });

      if (response.status === 401) {
        handleLogout();
        throw new Error('Session expired -- please sign in again.');
      }
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error("No reader");

      // SSE frames are separated by double-newline (\r\n\r\n).
      // Each frame has one or more lines: "event: <type>\r\ndata: <json>\r\n"
      // We accumulate a buffer across read() calls because a single chunk may
      // contain partial frames or multiple frames.
      let buffer = '';

      const parseSSEBuffer = (buf: string) => {
        // Split on double newline to get complete frames, keep the remainder
        const parts = buf.split(/\r?\n\r?\n/);
        const remainder = parts.pop() ?? ''; // last element may be incomplete
        for (const frame of parts) {
          if (!frame.trim()) continue;
          let eventType = 'message';
          let eventData = '';
          for (const line of frame.split(/\r?\n/)) {
            if (line.startsWith('event: '))     eventType = line.slice(7).trim();
            else if (line.startsWith('data: ')) eventData = line.slice(6).trim();
          }
          if (!eventData) continue;

          try {
            const data = JSON.parse(eventData);
            setMessages(prev => prev.map(msg => {
              if (msg.id !== assistantMsgId) return msg;
              if (eventType === 'ping') return msg; // keepalive, ignore
              if (eventType === 'progress' && data.status) {
                return { ...msg, status: data.status.replace(/_/g, ' ') };
              }
              if (eventType === 'evidence' && Array.isArray(data)) {
                return { ...msg, evidence: data };
              }
              if (eventType === 'visualization' && data) {
                return { ...msg, visualization: data };
              }
              if (eventType === 'token' && data.token !== undefined) {
                return { ...msg, content: data.token, isStreaming: false, status: undefined };
              }
              if (eventType === 'done') {
                return { ...msg, isStreaming: false, status: undefined };
              }
              if (eventType === 'error' && data.error) {
                return { ...msg, content: `Error: ${data.error}`, isStreaming: false, status: undefined };
              }
              return msg;
            }));
          } catch (e) {
            console.error('Failed to parse SSE frame data:', eventData, e);
          }
        }
        return remainder;
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        buffer = parseSSEBuffer(buffer);
      }
      // Flush any remaining buffer content on stream close
      if (buffer.trim()) parseSSEBuffer(buffer + '\n\n');

    } catch (error) {
      console.error(error);
      setMessages(prev => prev.map(msg => 
        msg.id === assistantMsgId ? { ...msg, content: "Connection failed. Make sure the backend server is running on port 8000.", isStreaming: false, status: undefined } : msg
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
              <Shield color="white" size={20} />
            </div>
            <h1>PS-1 <span>CIS</span></h1>
          </header>

          <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }} aria-label="Main Navigation">
            <button
              type="button"
              onClick={() => setActiveView('query')}
              style={{
                width: '100%',
                border: 'none',
                textAlign: 'left',
                font: 'inherit',
                fontWeight: '700',
                padding: '12px',
                borderRadius: '12px',
                background: activeView === 'query' ? 'rgba(50, 98, 115, 0.08)' : 'transparent',
                color: activeView === 'query' ? 'var(--primary)' : 'var(--text-secondary)',
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
                fontWeight: '700',
                padding: '12px',
                borderRadius: '12px',
                background: activeView === 'dashboard' ? 'rgba(50, 98, 115, 0.08)' : 'transparent',
                color: activeView === 'dashboard' ? 'var(--primary)' : 'var(--text-secondary)',
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
                fontWeight: '700',
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
                Signed in as <strong style={{ color: 'var(--primary)' }}>{displayName}</strong>
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
                      {msg.role === 'assistant' ? <Shield size={20} color="var(--accent-primary)" /> : <Search size={20} color="var(--accent-primary)" />}
                    </div>
                    <div className="message-content-wrapper" style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '100%' }}>
                      
                      {msg.status && (
                        <div className="w-full max-w-lg mb-4 mt-2">
                          <div className="flex items-center justify-between mb-2">
                            <div className="status-pill inline-flex items-center gap-2 py-1 px-3 bg-primary/10 border border-primary/20 rounded-full text-xs text-primary">
                              <div className="pulse w-1.5 h-1.5 rounded-full bg-[#ff9f1c] animate-ping" />
                              <span className="capitalize font-medium text-[11px]">{msg.status}...</span>
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
                                      className={`w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-semibold transition-all duration-300 border ${
                                        isCompleted ? 'bg-[#326273] border-[#326273] text-white shadow-sm' :
                                        isActive ? 'bg-[#ffbf69]/20 border-[#ff9f1c] text-[#ff9f1c] animate-pulse' :
                                        'bg-muted border-border text-muted-foreground'
                                      }`}
                                    >
                                      {isCompleted ? '✓' : idx + 1}
                                    </div>
                                    <span 
                                      className={`text-[8px] mt-1.5 hidden md:block whitespace-nowrap transition-colors ${
                                        isActive ? 'text-[#ff9f1c] font-semibold' : isCompleted ? 'text-[#326273] font-medium' : 'text-muted-foreground'
                                      }`}
                                    >
                                      {step.label}
                                    </span>
                                  </div>
                                  {idx < PIPELINE_STEPS.length - 1 && (
                                    <div 
                                      className={`h-0.5 flex-1 mx-0.5 rounded transition-all duration-300 ${
                                        isCompleted ? 'bg-[#326273]' : 'bg-border'
                                      }`} 
                                    />
                                  )}
                                </React.Fragment>
                              );
                            })}
                          </div>
                        </div>
                      )}
                      
                      <div className="message-content">
                        {msg.content || (msg.isStreaming ? (
                          <div className="flex flex-col gap-2 py-1">
                            <div className="flex items-center gap-1.5 mb-1">
                              <span className="w-2 h-2 rounded-full bg-[#326273] animate-bounce" style={{ animationDelay: '0ms' }} />
                              <span className="w-2 h-2 rounded-full bg-[#ff9f1c] animate-bounce" style={{ animationDelay: '150ms' }} />
                              <span className="w-2 h-2 rounded-full bg-[#ffbf69] animate-bounce" style={{ animationDelay: '300ms' }} />
                            </div>
                            <div className="w-48 h-3 rounded bg-muted/60 animate-pulse" />
                            <div className="w-36 h-2.5 rounded bg-muted/40 animate-pulse" />
                          </div>
                        ) : '')}
                      </div>
                      
                      {msg.evidence && msg.evidence.length > 0 && (
                        <div className="evidence-card" style={{ background: 'transparent', border: 'none', padding: 0 }}>
                          <details className="evidence-details group" style={{ width: '100%' }}>
                            <summary className="evidence-summary cursor-pointer select-none list-none flex items-center justify-between py-2 border-b border-border">
                              <div className="flex items-center gap-2 text-foreground font-medium">
                                <Database size={14} className="text-primary" />
                                <span>Retrieved Evidence ({msg.evidence.length} Citations)</span>
                              </div>
                              <span className="text-xs text-muted-foreground group-open:rotate-180 transition-transform duration-200">▼</span>
                            </summary>
                            <div className="evidence-content grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
                              {msg.evidence.map((item, idx) => {
                                const confidenceColor = 
                                  item.confidence?.toLowerCase() === 'high' ? 'text-emerald-700 bg-emerald-50 border-emerald-200' :
                                  item.confidence?.toLowerCase() === 'medium' ? 'text-amber-700 bg-amber-50 border-amber-200' :
                                  'text-rose-700 bg-rose-50 border-rose-200';
                                return (
                                  <div key={idx} className="evidence-item p-3 rounded-lg border border-border bg-card shadow-sm flex flex-col gap-2">
                                    <div className="flex items-center justify-between border-b border-border pb-2">
                                      <span className="font-semibold text-xs text-primary">{item.fir_id || "No Case ID"}</span>
                                      {item.confidence && (
                                        <span className={`text-[9px] px-2 py-0.5 rounded-full border font-medium ${confidenceColor}`}>
                                          {item.confidence.toUpperCase()}
                                        </span>
                                      )}
                                    </div>
                                    <div className="text-xs space-y-1 text-muted-foreground">
                                      {item.data?.crime_type && <div><strong>Type:</strong> {item.data.crime_type}</div>}
                                      {item.data?.district && <div><strong>District:</strong> {item.data.district}</div>}
                                      {item.data?.Date && <div><strong>Date:</strong> {item.data.Date}</div>}
                                      {item.data?.weapon && <div><strong>Weapon:</strong> {item.data.weapon}</div>}
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
                <form onSubmit={handleSubmit} className="input-box">
                  <button type="button" className="action-btn" aria-label="Attach file">
                    <Paperclip size={20} />
                  </button>
                  <input 
                    type="text" 
                    placeholder="Ask about cases, sections, or criminals..." 
                    value={inputValue}
                    onChange={e => setInputValue(e.target.value)}
                    disabled={isLoading}
                  />
                  <button type="button" className="action-btn" aria-label="Voice input">
                    <Mic size={20} />
                  </button>
                  <button type="submit" className="action-btn primary" disabled={!inputValue.trim() || isLoading} aria-label="Send message">
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
    </>
  );
}
