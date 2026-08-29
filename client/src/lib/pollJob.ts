// Recovers a job whose SSE stream was cut before it finished. AppSail closes the
// SSE response after ~45s; the pipeline keeps running server-side and writes its
// result to NoSQL, so we poll /api/query/status/:jobId until done/failed.
// Lifted verbatim from App.tsx's pollForCompletedJob.

import { fetchWithRetry } from './utils';
import type { EvidenceItem, Visualization } from '../types/chat';

export interface CompletedJob {
  status: string;
  answer?: string;
  evidence?: EvidenceItem[];
  visualization?: Visualization;
  error?: string;
}

export async function pollForCompletedJob(
  jobId: string,
  token: string | null,
  attempts = 300,
  intervalMs = 3000,
  baseUrl?: string,
): Promise<CompletedJob | null> {
  const base = baseUrl ?? (import.meta as any).env?.VITE_API_BASE_URL ?? '';
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetchWithRetry(`${base}/api/query/status/${jobId}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      } as RequestInit);
      if (res.ok) {
        const data = await res.json();
        if (data.status === 'done' || data.status === 'failed') return data;
      }
    } catch (err) {
      console.error('Job status poll failed:', err);
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return null;
}
