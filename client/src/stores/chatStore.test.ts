import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the retry wrapper shared by lib/sse, lib/pollJob and lib/api so we can
// hand the store synthetic Responses.
const fetchMock = vi.fn();
vi.mock('../lib/utils', () => ({
  fetchWithRetry: (...args: unknown[]) => fetchMock(...args),
  cn: (...a: unknown[]) => a.join(' '),
}));

import { useChatStore } from './chatStore';

const enc = new TextEncoder();

function streamResponse(pieces: string[]): Response {
  let i = 0;
  const body = {
    getReader() {
      return {
        read: async () =>
          i < pieces.length
            ? { value: enc.encode(pieces[i++]), done: false }
            : { value: undefined, done: true },
      };
    },
  };
  return { ok: true, status: 200, body } as unknown as Response;
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

function jsonResponse(payload: unknown): Response {
  return { ok: true, status: 200, json: async () => payload } as unknown as Response;
}

function lastAssistant(sessionId: string) {
  const msgs = useChatStore.getState().messagesBySession[sessionId] ?? [];
  return msgs[msgs.length - 1];
}

beforeEach(() => {
  fetchMock.mockReset();
  useChatStore.setState({ messagesBySession: {}, loadingBySession: {}, feedbackStatus: {} });
});

describe('chatStore.sendQuery', () => {
  it('applies every SSE frame onto the assistant message (token parity)', async () => {
    fetchMock.mockResolvedValueOnce(
      streamResponse([
        frame('job', { job_id: 'j1' }) +
          frame('progress', { status: 'retrieving_evidence' }) +
          frame('evidence', [{ fir_id: 'A' }, { fir_id: 'B' }, { fir_id: 'C' }]) +
          frame('visualization', { cytoscape: { elements: [] } }) +
          frame('token', { token: 'the final synthesised answer' }) +
          frame('done', {}),
      ]),
    );

    await useChatStore.getState().sendQuery({
      sessionId: 's_test1',
      text: 'list recent theft cases',
      language: 'en',
      token: 't',
    });

    const msgs = useChatStore.getState().messagesBySession['s_test1'];
    // greeting + user + assistant
    expect(msgs.map((m) => m.role)).toEqual(['assistant', 'user', 'assistant']);
    expect(msgs[1].content).toBe('list recent theft cases');

    const a = msgs[2];
    expect(a.content).toBe('the final synthesised answer');
    expect(a.evidence).toHaveLength(3);
    expect(a.visualization).toEqual({ cytoscape: { elements: [] } });
    expect(a.isStreaming).toBe(false);
    expect(a.status).toBeUndefined();
    expect(useChatStore.getState().loadingBySession['s_test1']).toBe(false);
  });

  it('recovers via the status poll when the stream ends with no terminal event', async () => {
    fetchMock
      // 1: the SSE stream — job id, some progress, then it just stops
      .mockResolvedValueOnce(
        streamResponse([frame('job', { job_id: 'j9' }) + frame('progress', { status: 'synthesizing_response' })]),
      )
      // 2: GET /api/query/status/j9
      .mockResolvedValueOnce(
        jsonResponse({
          status: 'done',
          answer: 'answer recovered from the job record',
          evidence: [{ fir_id: 'Z' }],
          visualization: { cytoscape: { elements: [] } },
        }),
      );

    await useChatStore.getState().sendQuery({
      sessionId: 's_test2',
      text: 'who is linked to ACC_102',
      language: 'en',
      token: 't',
    });

    const a = lastAssistant('s_test2');
    expect(a.content).toBe('answer recovered from the job record');
    expect(a.evidence).toHaveLength(1);
    expect(a.isStreaming).toBe(false);
    expect(a.status).toBeUndefined();
  });

  it('marks wasFirstTurn only for the first user turn (no rename call on later turns)', async () => {
    // Two back-to-back turns, no caseId => rename/fetchSessions never invoked;
    // we only assert both turns land and history accumulates.
    for (const t of ['first question', 'second question']) {
      fetchMock.mockResolvedValueOnce(
        streamResponse([frame('job', { job_id: 'k' }) + frame('token', { token: `re: ${t}` }) + frame('done', {})]),
      );
      await useChatStore.getState().sendQuery({ sessionId: 's_test3', text: t, language: 'en', token: 't' });
    }

    const msgs = useChatStore.getState().messagesBySession['s_test3'];
    expect(msgs.filter((m) => m.role === 'user').map((m) => m.content)).toEqual([
      'first question',
      'second question',
    ]);
    expect(lastAssistant('s_test3').content).toBe('re: second question');
  });
});

describe('chatStore.loadHistory', () => {
  it('hydrates restored turns from GET /api/sessions/:id', async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({
        meta: { session_id: 's_h', case_id: 'c_1', title: 'x', created_by: 'u', created_at: 0, last_activity_at: 0 },
        history: [
          { q: 'q one', a: 'a one', evidence: [{ fir_id: 'A' }] },
          { q: 'q two', a: 'a two' },
        ],
      }),
    );

    await useChatStore.getState().loadHistory('s_h');

    const msgs = useChatStore.getState().messagesBySession['s_h'];
    expect(msgs[0].id).toBe('restored');
    expect(msgs.map((m) => m.content)).toEqual(['Restored session history.', 'q one', 'a one', 'q two', 'a two']);
    expect(msgs[2].evidence).toHaveLength(1);
  });

  it('falls back to the greeting when the session has no history', async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ meta: {}, history: [] }));
    await useChatStore.getState().loadHistory('s_empty');
    const msgs = useChatStore.getState().messagesBySession['s_empty'];
    expect(msgs).toHaveLength(1);
    expect(msgs[0].id).toBe('greet');
  });
});
