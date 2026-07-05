import React, { useState, useRef, useEffect } from 'react';
import { Search, Mic, Paperclip, Send, Shield, Database, LayoutDashboard, Settings, Loader2, LogOut } from 'lucide-react';
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
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-icon">
              <Shield color="white" size={20} />
            </div>
            <h1>PS-1 <span>CIS</span></h1>
          </div>

          <nav style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            <div onClick={() => setActiveView('query')} style={{ padding: '12px', borderRadius: '12px', background: activeView === 'query' ? 'rgba(255,255,255,0.05)' : 'transparent', color: activeView === 'query' ? 'white' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
               <Search size={18} /> Active Query
            </div>
            <div onClick={() => setActiveView('dashboard')} style={{ padding: '12px', borderRadius: '12px', background: activeView === 'dashboard' ? 'rgba(255,255,255,0.05)' : 'transparent', color: activeView === 'dashboard' ? 'white' : 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
               <LayoutDashboard size={18} /> Dashboard
            </div>
            <div style={{ padding: '12px', borderRadius: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
               <Database size={18} /> Data Store
            </div>
          </nav>

          <div style={{ marginTop: 'auto' }}>
            {displayName && (
              <div style={{ padding: '12px', color: 'var(--text-secondary)', fontSize: '0.85rem' }}>
                Signed in as <strong style={{ color: 'white' }}>{displayName}</strong>
              </div>
            )}
            <div style={{ padding: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
               <Settings size={18} /> Settings
            </div>
            <div onClick={handleLogout} style={{ padding: '12px', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: '12px', cursor: 'pointer' }}>
               <LogOut size={18} /> Sign Out
            </div>
          </div>
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
                    <div className="status-pill">
                      <div className="pulse" />
                      <span style={{ textTransform: 'capitalize' }}>{msg.status}...</span>
                    </div>
                  )}
                  
                  <div className="message-content">
                    {msg.content || (msg.isStreaming ? <Loader2 className="animate-spin" size={16} /> : '')}
                  </div>
                  
                  {msg.evidence && msg.evidence.length > 0 && (
                    <div className="evidence-card">
                       <div className="evidence-header">
                         <Database size={14} /> Retrieved Evidence
                       </div>
                       <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word', color: 'var(--text-secondary)' }}>
                         {JSON.stringify(msg.evidence, null, 2)}
                       </pre>
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div ref={messagesEndRef} />
          </div>

          <div className="input-area">
            <form onSubmit={handleSubmit} className="input-box">
              <button type="button" className="action-btn">
                <Paperclip size={20} />
              </button>
              <input 
                type="text" 
                placeholder="Ask about cases, sections, or criminals..." 
                value={inputValue}
                onChange={e => setInputValue(e.target.value)}
                disabled={isLoading}
              />
              <button 
                type="button" 
                className={`action-btn ${isRecording ? 'recording' : ''}`}
                onClick={handleMicClick}
                style={isRecording ? { color: '#ff4444', animation: 'pulse 1.5s infinite' } : {}}
                disabled={isLoading && !isRecording}
              >
                <Mic size={20} />
              </button>
              <button type="submit" className="action-btn primary" disabled={!inputValue.trim() || isLoading}>
                <Send size={18} />
              </button>
            </form>
          </div>
          </>
          ) : (
            <DashboardPanel visualization={messages.filter(m => m.role === 'assistant').pop()?.visualization} />
          )}
        </main>
      </div>
    </>
  );
}
