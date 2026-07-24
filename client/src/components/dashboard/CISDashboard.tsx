import React, { useState, useEffect, useRef } from 'react';
import { useEntityDrawer } from '../../hooks/useEntityDrawer';
import { Shield, Mic, Square, Volume2, HelpCircle } from 'lucide-react';
import { RecentConversations } from '../recent-conversations';

const generateUUIDv4 = (): string => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
};

const BLOCKED_KEYWORDS = /\b(create|delete|drop|insert|alter|truncate|merge)\b/i;

interface EvidenceItem {
  id: string;
  text: string;
  original_text?: string;
  language?: string | null;
  is_translated?: boolean;
}

export default function CISDashboard() {
  const [sessionId] = useState<string>(generateUUIDv4);
  const [query, setQuery] = useState<string>('');
  const [language, setLanguage] = useState<string>('kn');
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [validationError, setValidationError] = useState<string | null>(null);
  
  const [streamedStatus, setStreamedStatus] = useState<string>('');
  const [finalReport, setFinalReport] = useState<string>('');
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [toggleOriginal, setToggleOriginal] = useState<{ [key: string]: boolean }>({});

  const [isPlayingTTS, setIsPlayingTTS] = useState<boolean>(false);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const ttsAudioRef = useRef<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (BLOCKED_KEYWORDS.test(query)) {
      setValidationError("Query contains blocked database modification keywords.");
    } else {
      setValidationError(null);
    }
  }, [query]);

  const startRecording = async () => {
    audioChunksRef.current = [];
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) audioChunksRef.current.push(event.data);
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: 'audio/webm' });
        await uploadAudioForTranscription(audioBlob);
        stream.getTracks().forEach(track => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
    } catch (err) {
      console.error("Microphone access denied:", err);
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const uploadAudioForTranscription = async (audioBlob: Blob) => {
    setIsLoading(true);
    const formData = new FormData();
    formData.append('audio', audioBlob, 'recording.webm');
    formData.append('language', language);

    try {
      const response = await fetch('/api/transcribe', {
        method: 'POST',
        body: formData,
      });
      if (!response.ok) throw new Error(`Transcription failed: ${response.statusText}`);
      const data = await response.json();
      if (data.transcript) {
        setQuery(data.transcript);
      }
    } catch (err) {
      console.error("ASR transmission error:", err);
    } finally {
      setIsLoading(false);
    }
  };

  const handleQuerySubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim() || validationError) return;

    setIsLoading(true);
    setStreamedStatus('Dispatching pipeline execution...');
    setFinalReport('');
    setEvidenceList([]);

    try {
      const authToken = sessionStorage.getItem("ps1_auth_token");
      const response = await fetch('/api/query', {
        method: 'POST',
        headers: { 
          'Content-Type': 'application/json',
          ...(authToken ? { 'Authorization': `Bearer ${authToken}` } : {})
        },
        body: JSON.stringify({ session_id: sessionId, query: query.trim() }),
      });

      if (!response.ok) {
        if (response.status === 401) {
          throw new Error("Authentication required. Please sign in.");
        }
        throw new Error(`Server returned ${response.status}`);
      }
      if (!response.body) throw new Error("No response body stream available.");
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      const parseSSEBuffer = (buf: string) => {
        const parts = buf.split(/\r?\n\r?\n/);
        const remainder = parts.pop() ?? '';
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
            if (eventType === 'progress' && data.status) {
              setStreamedStatus(data.status.replace(/_/g, ' '));
            } else if (eventType === 'evidence' && Array.isArray(data)) {
              setEvidenceList(data);
            } else if (eventType === 'token' && data.token !== undefined) {
              setFinalReport(data.token);
            } else if (eventType === 'error' && data.error) {
              setStreamedStatus(`Error: ${data.error}`);
            }
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
      if (buffer.trim()) parseSSEBuffer(buffer + '\n\n');
    } catch (err: any) {
      console.error("Streaming error:", err);
      setStreamedStatus(err.message || "Pipeline transmission breakdown.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleTTSPlayback = () => {
    if (!finalReport && !streamedStatus) return;
    if (isPlayingTTS) {
      ttsAudioRef.current?.pause();
      setIsPlayingTTS(false);
      return;
    }

    const targetText = finalReport || streamedStatus;
    const utterance = new SpeechSynthesisUtterance(targetText);
    
    if (language === 'kn') utterance.lang = 'kn-IN';
    else if (language === 'hi') utterance.lang = 'hi-IN';
    else utterance.lang = 'en-US';

    utterance.onend = () => setIsPlayingTTS(false);
    utterance.onerror = () => setIsPlayingTTS(false);
    
    setIsPlayingTTS(true);
    window.speechSynthesis.speak(utterance);
  };

  const getLanguageName = (code: string) => {
    if (code === 'kn') return 'Kannada';
    if (code === 'hi') return 'Hindi';
    return 'English';
  };

  return (
    <div className="overflow-y-auto h-full w-full flex flex-col gap-8 animate-fade-in font-sans" style={{ padding: '40px 10% 40px 40px', color: '#4a453e' }}>
      
      {/* Structural Headers */}
      <div>
        <h2 className="stamp-font text-3xl tracking-tight mb-1" style={{ color: '#2b2824' }}>CIS Execution Console</h2>
        <p className="text-sm font-mono text-stone-500">
          Direct system pipeline deployment interface. Current Token: <span className="font-mono text-red-700/90">{sessionId}</span>
        </p>
      </div>

      {/* 1. VOICE INPUT WITH LANGUAGE PICKER */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-mono font-bold tracking-wider uppercase text-red-800/80">1. Voice Input with Language Picker</span>
        <form onSubmit={handleQuerySubmit} className="flex items-center w-full p-1.5 bg-[#f4ece1] rounded border" style={{ borderColor: '#d1c7b7' }}>
          
          {/* Internal Language Grid Segment */}
          <div className="flex items-center bg-[#eae1d4] p-0.5 rounded border border-[#d1c7b7]/60 mr-3">
            {[
              { code: 'en', label: 'EN' },
              { code: 'hi', label: 'HI' },
              { code: 'kn', label: 'KN' }
            ].map((lang) => (
              <button
                key={lang.code}
                type="button"
                onClick={() => setLanguage(lang.code)}
                className={`w-8 h-7 text-xs font-mono font-bold rounded flex items-center justify-center transition-all`}
                style={{
                  background: language === lang.code ? '#802323' : 'transparent',
                  color: language === lang.code ? '#fdfbf7' : '#6e655a',
                  border: language === lang.code ? '1px solid #631919' : 'none'
                }}
              >
                {lang.label}
              </button>
            ))}
          </div>

          {/* Text input area field */}
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask about cases, sections, or criminals..."
            className="flex-1 bg-transparent py-2 text-sm focus:outline-none placeholder-stone-400 font-medium"
            style={{ color: '#2b2824' }}
            disabled={isLoading}
          />

          {/* Inline Media Button Trigger */}
          <button
            type="button"
            onClick={isRecording ? stopRecording : startRecording}
            className="p-2 text-stone-500 hover:text-stone-800 mr-2 transition-colors"
          >
            {isRecording ? <Square size={16} className="text-red-700 fill-red-700 animate-pulse" /> : <Mic size={18} />}
          </button>

          {/* Solid Action Square Submit Box */}
          <button
            type="submit"
            disabled={isLoading || !query.trim() || !!validationError}
            className="w-10 h-10 rounded flex items-center justify-center transition-all bg-[#802323] hover:bg-[#631919]"
            style={{ opacity: (isLoading || !query.trim() || !!validationError) ? 0.4 : 1 }}
          >
            <div className="w-3 h-3 border-2 border-white rotate-45 transform translate-x-[-0.5px]"></div>
          </button>
        </form>

        {validationError && (
          <div className="text-xs p-2.5 rounded font-mono border bg-red-50 text-red-800 border-red-200">
            ⚠ System Exception: {validationError}
          </div>
        )}
      </div>

      {/* 2. FIELD REPORT WITH LISTEN CONTROL */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-mono font-bold tracking-wider uppercase text-red-800/80">2. Field Report with Listen Control</span>
        <div className="flex gap-4">
          <div className="message-avatar">
            <Shield size={20} color="var(--accent-primary)" />
          </div>
          <div className="message-content relative flex-1 flex flex-col gap-4">
            
            {/* Floating Dossier Tag Header */}
            <div className="absolute top-0 left-4 transform -translate-y-1/2 bg-[#f4ece1] border px-2 py-0.5 text-[10px] font-mono tracking-wider font-bold uppercase text-stone-600 rounded-sm" style={{ borderColor: '#d1c7b7' }}>
              Field Report
            </div>

            <div className="text-[17px] font-serif leading-relaxed text-stone-800 mt-1">
              {finalReport || streamedStatus || "System idle. Awaiting operational pipeline execution payload..."}
            </div>

            {(finalReport || streamedStatus) && (
              <div className="flex items-center gap-4 mt-2 pt-4 border-t border-dashed border-stone-200" style={{ borderColor: 'var(--glass-border)' }}>
                <button
                  onClick={handleTTSPlayback}
                  className="flex items-center gap-2 group text-xs font-mono font-bold transition-colors"
                  style={{ color: 'var(--text-secondary)' }}
                >
                  <div className={`w-6 h-6 rounded-full border flex items-center justify-center transition-colors ${isPlayingTTS ? 'bg-red-50 text-red-700 border-red-400' : 'border-stone-400 group-hover:border-stone-700'}`}>
                    <Volume2 size={12} />
                  </div>
                  <span>{isPlayingTTS ? 'Mute Audio' : 'Listen'}</span>
                </button>
                <span className="text-xs font-mono text-stone-400">•</span>
                <span className="text-xs font-mono font-semibold" style={{ color: 'var(--text-secondary)' }}>{getLanguageName(language)}</span>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 3. EVIDENCE TABLE */}
      <div className="flex flex-col gap-2">
        <span className="text-xs font-mono font-bold tracking-wider uppercase text-red-800/80">3. Evidence</span>
        
        {evidenceList.length === 0 ? (
          <div className="p-8 border border-dashed rounded text-center font-mono text-xs text-stone-400 bg-[#fdfbf7]/40" style={{ borderColor: '#d1c7b7' }}>
            No active source cross-citations mapped to block.
          </div>
        ) : (
          <RecentConversations evidence={evidenceList} />
        )}
      </div>

    </div>
  );
}
