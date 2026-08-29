import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock the retry wrapper so we can hand streamQuery a synthetic Response.
const fetchMock = vi.fn();
vi.mock('./utils', () => ({
  fetchWithRetry: (...args: unknown[]) => fetchMock(...args),
}));

import { streamQuery, type StreamQueryHandlers } from './sse';

const enc = new TextEncoder();

/** A Response whose body streams the given string pieces, one per read(). */
function streamResponse(pieces: string[], init: Partial<Response> = {}): Response {
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
  return { ok: true, status: 200, body, ...init } as unknown as Response;
}

function frame(event: string, data: unknown): string {
  return `event: ${event}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`;
}

function spyHandlers() {
  const calls: string[] = [];
  const h: StreamQueryHandlers = {
    onJob: (id) => calls.push(`job:${id}`),
    onProgress: (s) => calls.push(`progress:${s}`),
    onEvidence: (e) => calls.push(`evidence:${e.length}`),
    onVisualization: () => calls.push('visualization'),
    onToken: (t) => calls.push(`token:${t}`),
    onDone: () => calls.push('done'),
    onError: (m) => calls.push(`error:${m}`),
    onUnauthorized: () => calls.push('unauthorized'),
  };
  return { h, calls };
}

const params = { sessionId: 's_abc', query: 'hi', language: 'en', token: 't', baseUrl: '' };

beforeEach(() => fetchMock.mockReset());

describe('streamQuery', () => {
  it('parses multiple frames delivered in one chunk, in order', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue(
      streamResponse([
        frame('job', { job_id: 'j1' }) +
          frame('progress', { status: 'retrieving_evidence' }) +
          frame('evidence', [{ fir_id: 'A' }, { fir_id: 'B' }]) +
          frame('visualization', { cytoscape: { elements: [] } }) +
          frame('token', { token: 'final answer' }) +
          frame('done', {}),
      ]),
    );

    const res = await streamQuery(params, h);

    expect(calls).toEqual([
      'job:j1',
      'progress:retrieving evidence', // underscores normalised
      'evidence:2',
      'visualization',
      'token:final answer',
      'done',
    ]);
    expect(res).toEqual({ jobId: 'j1', sawTerminalEvent: true });
  });

  it('reassembles a frame split across two chunks', async () => {
    const { h, calls } = spyHandlers();
    const full = frame('job', { job_id: 'j2' }) + frame('token', { token: 'hello world' }) + frame('done', {});
    const cut = Math.floor(full.length / 2);
    fetchMock.mockResolvedValue(streamResponse([full.slice(0, cut), full.slice(cut)]));

    const res = await streamQuery(params, h);

    expect(calls).toEqual(['job:j2', 'token:hello world', 'done']);
    expect(res.sawTerminalEvent).toBe(true);
  });

  it('ignores ping keepalives', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue(
      streamResponse([frame('job', { job_id: 'j3' }) + frame('ping', {}) + frame('token', { token: 'x' })]),
    );
    await streamQuery(params, h);
    expect(calls).toEqual(['job:j3', 'token:x']);
  });

  it('returns sawTerminalEvent=false when the stream ends with no done/error', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue(
      streamResponse([frame('job', { job_id: 'j4' }) + frame('progress', { status: 'confidence_scoring' })]),
    );

    const res = await streamQuery(params, h);

    expect(res).toEqual({ jobId: 'j4', sawTerminalEvent: false });
    expect(calls).toEqual(['job:j4', 'progress:confidence scoring']);
  });

  it('flushes a trailing frame with no closing blank line', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue(
      streamResponse(['event: token\r\ndata: {"token":"tail"}']), // no trailing \r\n\r\n
    );
    await streamQuery(params, h);
    expect(calls).toEqual(['token:tail']);
  });

  it('surfaces an error frame without throwing', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue(streamResponse([frame('error', { error: 'pipeline exploded' })]));
    const res = await streamQuery(params, h);
    expect(calls).toEqual(['error:pipeline exploded']);
    expect(res.sawTerminalEvent).toBe(true);
  });

  it('calls onUnauthorized and throws on 401', async () => {
    const { h, calls } = spyHandlers();
    fetchMock.mockResolvedValue({ ok: false, status: 401 } as Response);
    await expect(streamQuery(params, h)).rejects.toThrow(/sign in again/);
    expect(calls).toEqual(['unauthorized']);
  });

  it('throws on a non-401 HTTP error', async () => {
    const { h } = spyHandlers();
    fetchMock.mockResolvedValue({ ok: false, status: 500 } as Response);
    await expect(streamQuery(params, h)).rejects.toThrow(/status: 500/);
  });
});
