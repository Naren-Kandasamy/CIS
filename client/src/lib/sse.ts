// SSE streaming for POST /api/query, lifted verbatim out of App.tsx's
// handleSubmit so it can be unit-tested and, later, driven by the chat store
// instead of a component. The frame parser, the cross-read buffer, the job-id
// capture and the terminal-event flag all behave exactly as before.

import { fetchWithRetry } from './utils';
import type { EvidenceItem, Visualization } from '../types/chat';

export interface StreamQueryParams {
  sessionId: string;
  query: string;
  language: string;
  token: string | null;
  /** Defaults to import.meta.env.VITE_API_BASE_URL || ''. */
  baseUrl?: string;
}

export interface StreamQueryHandlers {
  onJob?: (jobId: string) => void;
  /** Human-readable stage, underscores already replaced with spaces. */
  onProgress?: (status: string) => void;
  onEvidence?: (evidence: EvidenceItem[]) => void;
  onVisualization?: (visualization: Visualization) => void;
  onToken?: (token: string) => void;
  onDone?: () => void;
  onError?: (message: string) => void;
  /** Called before the 401 error is thrown, so the caller can sign out. */
  onUnauthorized?: () => void;
}

export interface StreamQueryResult {
  jobId: string | null;
  sawTerminalEvent: boolean;
}

export async function streamQuery(
  params: StreamQueryParams,
  handlers: StreamQueryHandlers,
): Promise<StreamQueryResult> {
  const base = params.baseUrl ?? (import.meta as any).env?.VITE_API_BASE_URL ?? '';

  const response = await fetchWithRetry(`${base}/api/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${params.token}`,
    },
    body: JSON.stringify({
      session_id: params.sessionId,
      query: params.query,
      language: params.language,
    }),
  });

  if (response.status === 401) {
    handlers.onUnauthorized?.();
    throw new Error('Session expired -- please sign in again.');
  }
  if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();
  if (!reader) throw new Error('No reader');

  // Tracked so a prematurely-closed stream can be recovered by the caller.
  let jobId: string | null = null;
  let sawTerminalEvent = false;

  // SSE frames are separated by a blank line (\r\n\r\n). Each frame is one or
  // more "event: <type>" / "data: <json>" lines. A single read() chunk may hold
  // a partial frame or several frames, so we keep a buffer across reads.
  let buffer = '';

  const parseSSEBuffer = (buf: string): string => {
    const parts = buf.split(/\r?\n\r?\n/);
    const remainder = parts.pop() ?? ''; // last element may be incomplete
    for (const frame of parts) {
      if (!frame.trim()) continue;
      let eventType = 'message';
      let eventData = '';
      for (const line of frame.split(/\r?\n/)) {
        if (line.startsWith('event: ')) eventType = line.slice(7).trim();
        else if (line.startsWith('data: ')) eventData = line.slice(6).trim();
      }
      if (!eventData) continue;

      try {
        const data = JSON.parse(eventData);

        // Emitted first by the server. Retained so a stream cut short by the
        // AppSail response timeout can still be recovered by the caller.
        if (eventType === 'job' && data.job_id) {
          jobId = data.job_id;
          handlers.onJob?.(data.job_id);
          continue;
        }
        if (eventType === 'done' || eventType === 'error') sawTerminalEvent = true;

        if (eventType === 'ping') continue; // keepalive
        if (eventType === 'progress' && data.status) {
          handlers.onProgress?.(String(data.status).replace(/_/g, ' '));
        } else if (eventType === 'evidence' && Array.isArray(data)) {
          handlers.onEvidence?.(data);
        } else if (eventType === 'visualization' && data) {
          handlers.onVisualization?.(data);
        } else if (eventType === 'token' && data.token !== undefined) {
          handlers.onToken?.(data.token);
        } else if (eventType === 'done') {
          handlers.onDone?.();
        } else if (eventType === 'error' && data.error) {
          handlers.onError?.(String(data.error));
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
  // Flush any trailing frame on stream close.
  if (buffer.trim()) parseSSEBuffer(buffer + '\n\n');

  return { jobId, sawTerminalEvent };
}
