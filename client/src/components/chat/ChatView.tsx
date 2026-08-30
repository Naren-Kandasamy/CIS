import type { Message, QueryLanguage } from '../../types/chat';
import { MessageList } from './MessageList';
import { InputBar } from './InputBar';

// Phase 3: chat layout shell -- transcript above, composer below. Extracted from
// SessionChatPage (originally the inline block in App.tsx).

interface ChatViewProps {
  messages: Message[];
  sessionId?: string;
  isLoading: boolean;
  onSend: (text: string, language: QueryLanguage) => void | Promise<void>;
}

export function ChatView({ messages, sessionId, isLoading, onSend }: ChatViewProps) {
  return (
    <div className="chat-container">
      <MessageList messages={messages} sessionId={sessionId} />
      <InputBar disabled={isLoading} onSend={onSend} />
    </div>
  );
}
