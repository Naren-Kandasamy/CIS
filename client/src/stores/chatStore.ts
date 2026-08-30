import { create } from 'zustand';
import type { Message } from '../types/chat';
import { streamQuery } from '../lib/sse';
import { pollForCompletedJob } from '../lib/pollJob';
import { apiFetch, getSession, renameSession } from '../lib/api';
import { useCasesStore } from './casesStore';

// Phase 2: the chat's per-session message state, lifted out of SessionChatPage.
// The SSE loop patches a message ~10x per query; keeping that state here (outside
// the React tree) means the stream handlers call
// useChatStore.getState().patchMessage(...) with no stale closures -- the hazard
// the old updateSessionMessages(prev => ...) had when it captured targetSessionId.
//
// The message-patch reducer bodies are byte-identical to Phase 1's `patch(...)`
// calls; only the place the state lives has moved.

const greeting = (): Message[] => [
  {
    id: 'greet',
    role: 'assistant',
    content: 'Session ready. Ask about cases, sections, suspects or locations for this file.',
  },
];

export type FeedbackVerdict = 'confirmed' | 'corrected';

interface SendQueryArgs {
  sessionId: string;
  caseId?: string;
  text: string;
  language: string;
  token: string | null;
  onUnauthorized?: () => void;
}

interface SubmitFeedbackArgs {
  sessionId: string | undefined;
  item: NonNullable<Message['evidence']>[number];
  verdict: FeedbackVerdict;
  explanation?: string;
  queryText: string;
  officerId: string;
}

interface ChatState {
  messagesBySession: Record<string, Message[]>;
  loadingBySession: Record<string, boolean>;
  feedbackStatus: Record<string, { verdict: FeedbackVerdict }>;

  /** Reset to greeting + hydrate from GET /api/sessions/:id. */
  loadHistory: (sessionId: string) => Promise<void>;
  patchMessage: (sessionId: string, id: string, fn: (m: Message) => Message) => void;
  sendQuery: (args: SendQueryArgs) => Promise<void>;
  submitFeedback: (args: SubmitFeedbackArgs) => Promise<boolean>;
}

export const useChatStore = create<ChatState>((set, get) => ({
  messagesBySession: {},
  loadingBySession: {},
  feedbackStatus: {},

  loadHistory: async (sessionId) => {
    set((s) => ({ messagesBySession: { ...s.messagesBySession, [sessionId]: greeting() } }));
    try {
      const data = await getSession(sessionId);
      const history = data.history ?? [];
      if (history.length === 0) return;
      set((s) => ({
        messagesBySession: {
          ...s.messagesBySession,
          [sessionId]: [
            { id: 'restored', role: 'assistant', content: 'Restored session history.' },
            ...history.flatMap((h, idx) => [
              { id: `hist-${idx}-u`, role: 'user' as const, content: h.q },
              {
                id: `hist-${idx}-a`,
                role: 'assistant' as const,
                content: h.a,
                evidence: h.evidence as Message['evidence'],
                visualization: h.visualization as Message['visualization'],
              },
            ]),
          ],
        },
      }));
    } catch {
      /* leave the greeting in place */
    }
  },

  patchMessage: (sessionId, id, fn) =>
    set((s) => ({
      messagesBySession: {
        ...s.messagesBySession,
        [sessionId]: (s.messagesBySession[sessionId] ?? []).map((m) => (m.id === id ? fn(m) : m)),
      },
    })),

  sendQuery: async ({ sessionId, caseId, text, language, token, onUnauthorized }) => {
    const patch = (id: string, fn: (m: Message) => Message) =>
      get().patchMessage(sessionId, id, fn);

    const existing = get().messagesBySession[sessionId] ?? greeting();
    const wasFirstTurn = !existing.some((m) => m.role === 'user');

    const userMessage: Message = { id: crypto.randomUUID(), role: 'user', content: text };
    const assistantMsgId = crypto.randomUUID();

    set((s) => ({
      messagesBySession: {
        ...s.messagesBySession,
        [sessionId]: [
          ...existing,
          userMessage,
          { id: assistantMsgId, role: 'assistant', content: '', status: 'dispatching job', isStreaming: true },
        ],
      },
      loadingBySession: { ...s.loadingBySession, [sessionId]: true },
    }));

    try {
      const { jobId, sawTerminalEvent } = await streamQuery(
        { sessionId, query: text, language, token },
        {
          onUnauthorized,
          onProgress: (status) => patch(assistantMsgId, (m) => ({ ...m, status })),
          onEvidence: (evidence) => patch(assistantMsgId, (m) => ({ ...m, evidence })),
          onVisualization: (visualization) => patch(assistantMsgId, (m) => ({ ...m, visualization })),
          onToken: (tok) => patch(assistantMsgId, (m) => ({ ...m, content: tok, isStreaming: false, status: undefined })),
          onDone: () => patch(assistantMsgId, (m) => ({ ...m, isStreaming: false, status: undefined })),
          onError: (msg) =>
            patch(assistantMsgId, (m) => ({ ...m, content: `Error: ${msg}`, isStreaming: false, status: undefined })),
        },
      );

      if (!sawTerminalEvent && jobId) {
        const recovered = await pollForCompletedJob(jobId, token);
        patch(assistantMsgId, (m) =>
          recovered?.status === 'done'
            ? {
                ...m,
                content: recovered.answer ?? m.content,
                evidence: recovered.evidence ?? m.evidence,
                visualization: recovered.visualization ?? m.visualization,
                isStreaming: false,
                status: undefined,
              }
            : {
                ...m,
                content:
                  recovered?.error ??
                  'This query took longer than expected and the connection closed. Please try again.',
                isStreaming: false,
                status: undefined,
              },
        );
      }

      if (caseId) {
        useCasesStore.getState().touchCase(caseId);
        if (wasFirstTurn) {
          // Stamp the session title from the first query, then refresh the list.
          renameSession(sessionId, text.trim().slice(0, 80))
            .catch(() => {})
            .finally(() => {
              useCasesStore.getState().fetchSessions(caseId).catch(() => {});
            });
        }
      }
    } catch (error) {
      const message =
        error instanceof TypeError
          ? 'Unable to reach the server. Please check your connection and try again.'
          : 'Something went wrong while processing your query. Please try again.';
      patch(assistantMsgId, (m) => ({ ...m, content: message, isStreaming: false, status: undefined }));
    } finally {
      set((s) => ({ loadingBySession: { ...s.loadingBySession, [sessionId]: false } }));
    }
  },

  submitFeedback: async ({ sessionId, item, verdict, explanation, queryText, officerId }) => {
    const key = item.edge_id || item.fir_id;
    try {
      await apiFetch('/api/feedback/correction', {
        method: 'POST',
        body: {
          event_id: crypto.randomUUID(),
          session_id: sessionId,
          officer_id: officerId || 'officer',
          timestamp: new Date().toISOString(),
          query_text: queryText || '',
          edge_type: item.edge_type || 'NARRATIVE_SIMILARITY',
          crime_type: item.crime_type || null,
          edge_id: item.edge_id || null,
          verdict,
          explanation: explanation || null,
        },
      });
      set((s) => ({ feedbackStatus: { ...s.feedbackStatus, [key]: { verdict } } }));
      return true;
    } catch {
      return false;
    }
  },
}));
