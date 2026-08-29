import { Search, Shield } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import type { Message } from '../../types/chat';
import { PipelineProgress } from './PipelineProgress';
import { EvidencePanel, type EvidenceFeedback } from './EvidencePanel';

// Phase 3: one chat row (avatar + streaming stepper + markdown body + evidence),
// extracted verbatim from SessionChatPage's message map (originally App.tsx).

type EvidenceItem = NonNullable<Message['evidence']>[number];

interface MessageBubbleProps {
  message: Message;
  openEntity: (entity: {
    type: 'fir';
    id: string;
    label: string;
    data: Record<string, unknown>;
    evidenceItems: EvidenceItem[];
  }) => void;
  feedback: EvidenceFeedback;
}

export function MessageBubble({ message, openEntity, feedback }: MessageBubbleProps) {
  return (
    <div className={`message ${message.role}`}>
      <div className="message-avatar">
        {message.role === 'assistant' ? (
          <Shield size={20} color="var(--accent-primary)" />
        ) : (
          <Search size={20} color="white" />
        )}
      </div>
      <div
        className="message-content-wrapper"
        style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxWidth: '100%' }}
      >
        <PipelineProgress status={message.status} />

        <div className="message-content">
          {message.content ? (
            <ReactMarkdown>{message.content}</ReactMarkdown>
          ) : message.isStreaming ? (
            <div className="flex flex-col gap-2 py-1">
              <div className="flex items-center gap-1.5 mb-1">
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent-primary)', animationDelay: '0ms' }} />
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent-secondary)', animationDelay: '200ms' }} />
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: 'var(--accent-gold)', animationDelay: '400ms' }} />
              </div>
              <div className="w-48 h-3 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
              <div className="w-36 h-2.5 rounded animate-pulse" style={{ background: 'var(--glass-border)' }} />
            </div>
          ) : (
            ''
          )}
        </div>

        {message.evidence && message.evidence.length > 0 && (
          <EvidencePanel evidence={message.evidence} openEntity={openEntity} feedback={feedback} />
        )}
      </div>
    </div>
  );
}
