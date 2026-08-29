import { useEffect, useRef, useState } from 'react';
import type { Message } from '../../types/chat';
import { useAuthStore } from '../../stores/authStore';
import { useChatStore } from '../../stores/chatStore';
import { useEntityStore } from '../../stores/entityStore';
import { MessageBubble } from './MessageBubble';
import type { EvidenceFeedback } from './EvidencePanel';

// Phase 3: the scrolling transcript. Owns the "one correction box open at a
// time" state (originally lifted in SessionChatPage / App.tsx) and wires the
// evidence feedback round-trip through chatStore.

type EvidenceItem = NonNullable<Message['evidence']>[number];

export function MessageList({ messages, sessionId }: { messages: Message[]; sessionId?: string }) {
  const displayName = useAuthStore((s) => s.displayName);
  const openEntity = useEntityStore((s) => s.open);
  const feedbackStatus = useChatStore((s) => s.feedbackStatus);
  const submitFeedback = useChatStore((s) => s.submitFeedback);

  const [activeCorrectionId, setActiveCorrectionId] = useState<string | null>(null);
  const [correctionExplanation, setCorrectionExplanation] = useState('');

  const messagesEndRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleFeedbackSubmit = async (
    item: EvidenceItem,
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

  const feedback: EvidenceFeedback = {
    status: feedbackStatus,
    activeCorrectionId,
    explanation: correctionExplanation,
    onExplanationChange: setCorrectionExplanation,
    onOpenCorrection: (key) => {
      setActiveCorrectionId(key);
      setCorrectionExplanation('');
    },
    onCancelCorrection: () => setActiveCorrectionId(null),
    onSubmit: handleFeedbackSubmit,
  };

  return (
    <div className="chat-messages">
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} openEntity={openEntity} feedback={feedback} />
      ))}
      <div ref={messagesEndRef} />
    </div>
  );
}
