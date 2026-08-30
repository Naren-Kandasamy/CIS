import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import type { Message, QueryLanguage } from '../types/chat';
import { useAuthStore } from '../stores/authStore';
import { useChatStore } from '../stores/chatStore';
import { ChatView } from '../components/chat/ChatView';

const EMPTY: Message[] = [];

// Phase 3: this page is now a thin container. Message state lives in chatStore
// (keyed by :sessionId); the UI is composed from components/chat/*. Its only
// jobs: read the route id, hydrate history on id change, and hand sendQuery a
// send handler bound to this case/session.

export default function SessionChatPage() {
  const { caseId, sessionId } = useParams();
  const token = useAuthStore((s) => s.token);
  const logout = useAuthStore((s) => s.logout);

  const messages = useChatStore((s) => (sessionId ? s.messagesBySession[sessionId] : undefined) ?? EMPTY);
  const isLoading = useChatStore((s) => (sessionId ? s.loadingBySession[sessionId] : false) ?? false);
  const loadHistory = useChatStore((s) => s.loadHistory);
  const sendQuery = useChatStore((s) => s.sendQuery);

  // Load this session's history whenever the route id changes.
  useEffect(() => {
    if (!sessionId) return;
    loadHistory(sessionId);
  }, [sessionId, loadHistory]);

  const handleSend = async (text: string, language: QueryLanguage) => {
    if (!sessionId) return;
    await sendQuery({ sessionId, caseId, text, language, token, onUnauthorized: logout });
  };

  return (
    <ChatView messages={messages} sessionId={sessionId} isLoading={isLoading} onSend={handleSend} />
  );
}
