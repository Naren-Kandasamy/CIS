// Typed thin wrappers over fetchWithRetry. Collapses the ~15 copies of
// `${import.meta.env.VITE_API_BASE_URL || ''}/api/...` + manual Bearer header
// scattered across the app. The SSE query path stays in lib/sse.ts (it needs the
// raw ReadableStream); everything else goes through apiFetch here.

import { fetchWithRetry } from './utils';
import type {
  CasesResponse,
  SessionsResponse,
  SessionDetailResponse,
  BoardResponse,
  BoardLayoutResponse,
  HypothesesResponse,
  LoginResponse,
} from '../types/api';
import type { Case, SessionMeta } from '../types/case';
import type { HypothesisRecord, HypothesisCheckLog } from '../types/hypothesis';
import type { BoardCard } from '../types/board';

const AUTH_KEY = 'ps1_auth_token';

export function apiBase(): string {
  return (import.meta as any).env?.VITE_API_BASE_URL ?? '';
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

export interface ApiFetchOptions extends Omit<RequestInit, 'body'> {
  body?: unknown;
  /** Explicit bearer token; defaults to sessionStorage ps1_auth_token. */
  token?: string | null;
  /** Skip JSON parsing and return the raw Response. */
  raw?: boolean;
}

export async function apiFetch<T = unknown>(
  path: string,
  opts: ApiFetchOptions = {},
): Promise<T> {
  const { body, token, raw, headers, ...rest } = opts;
  const auth = token !== undefined ? token : sessionStorage.getItem(AUTH_KEY);

  const finalHeaders: Record<string, string> = { ...(headers as Record<string, string>) };
  if (auth) finalHeaders.Authorization = `Bearer ${auth}`;

  let finalBody: BodyInit | undefined;
  if (body instanceof FormData) {
    finalBody = body;
  } else if (body !== undefined) {
    finalHeaders['Content-Type'] = 'application/json';
    finalBody = JSON.stringify(body);
  }

  const res = await fetchWithRetry(`${apiBase()}${path}`, {
    ...rest,
    headers: finalHeaders,
    body: finalBody,
  });

  if (raw) return res as unknown as T;
  if (!res.ok) {
    let detail = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      if (j?.detail) detail = j.detail;
    } catch { /* non-JSON error body */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

// ─── auth ────────────────────────────────────────────────────────────────────
export const login = (username: string, password: string) =>
  apiFetch<LoginResponse>('/api/auth/login', {
    method: 'POST',
    body: { username, password },
    token: null,
  });

// ─── cases & sessions ───────────────────────────────────────────────────────
export const listCases = () => apiFetch<CasesResponse>('/api/cases');
export const createCase = (body: { title: string; crime_no?: string | null; district?: string | null }) =>
  apiFetch<Case>('/api/cases', { method: 'POST', body });
export const deleteCase = (caseId: string) =>
  apiFetch<{ status: string }>(`/api/cases/${caseId}`, { method: 'DELETE' });

export const listSessions = (caseId: string) =>
  apiFetch<SessionsResponse>(`/api/cases/${caseId}/sessions`);
export const createSession = (caseId: string) =>
  apiFetch<SessionMeta>(`/api/cases/${caseId}/sessions`, { method: 'POST' });
export const getSession = (sessionId: string) =>
  apiFetch<SessionDetailResponse>(`/api/sessions/${sessionId}`);
export const renameSession = (sessionId: string, title: string) =>
  apiFetch<SessionMeta>(`/api/sessions/${sessionId}`, { method: 'PATCH', body: { title } });
export const deleteSession = (sessionId: string) =>
  apiFetch<{ status: string }>(`/api/sessions/${sessionId}`, { method: 'DELETE' });

// ─── case board ─────────────────────────────────────────────────────────────
export const getBoard = (caseId: string) =>
  apiFetch<BoardResponse>(`/api/cases/${caseId}/board`);
export const pinToBoard = (
  caseId: string,
  body: { source_session_id: string; content_type: string; content: Record<string, unknown> },
) => apiFetch<{ status: string }>(`/api/cases/${caseId}/board`, { method: 'POST', body });
export const unpinFromBoard = (caseId: string, pinnedAt: number) =>
  apiFetch<{ status: string }>(`/api/cases/${caseId}/board`, {
    method: 'DELETE',
    body: { pinned_at: pinnedAt },
  });
export const getBoardLayout = (caseId: string) =>
  apiFetch<BoardLayoutResponse>(`/api/cases/${caseId}/board/layout`);
export const putBoardLayout = (caseId: string, cards: BoardCard[], dismissed: string[] = []) =>
  apiFetch<BoardLayoutResponse>(`/api/cases/${caseId}/board/layout`, {
    method: 'PUT',
    body: { cards, dismissed },
  });

// ─── entity relation network ────────────────────────────────────────────────
export interface GraphResponse {
  elements: { data: Record<string, unknown>; classes?: string }[];
  degraded?: boolean;
  reason?: string;
  case_count?: number;
  seed_fir_count?: number;
  shared_accused_count?: number;
  /** true when the thin-graph overview layer (top-connected accused) was appended */
  overview?: boolean;
  overview_note?: string | null;
}
/** Officer-wide graph — union across every case the caller collaborates on. */
export const getGlobalGraph = () => apiFetch<GraphResponse>('/api/graph');
/** One case's graph — nodes/edges reachable from its pinned FIRs + hypotheses. */
export const getCaseGraph = (caseId: string) =>
  apiFetch<GraphResponse>(`/api/cases/${caseId}/graph`);

// ─── hypotheses ─────────────────────────────────────────────────────────────
export const listCaseHypotheses = (caseId: string) =>
  apiFetch<HypothesesResponse>(`/api/cases/${caseId}/hypotheses`);
export const createCaseHypothesis = (
  caseId: string,
  body: {
    statement: string;
    detail?: string | null;
    linked_entity_ids: string[];
    fir_id?: string | null;
  },
) =>
  apiFetch<{ status: string; hypothesis: HypothesisRecord }>(`/api/cases/${caseId}/hypotheses`, {
    method: 'POST',
    body,
  });
export const listHypothesesByFir = (firId: string) =>
  apiFetch<HypothesesResponse & { fir_id: string }>(`/api/investigation/hypothesis/${firId}`);
export const createHypothesis = (body: {
  fir_id: string;
  statement: string;
  detail?: string | null;
  linked_entity_ids: string[];
  case_id?: string | null;
}) =>
  apiFetch<{ status: string; hypothesis: HypothesisRecord }>('/api/investigation/hypothesis', {
    method: 'POST',
    body,
  });
export const checkHypothesis = (hypothesisId: string) =>
  apiFetch<{ status: string; log: HypothesisCheckLog }>(
    `/api/investigation/hypothesis/${hypothesisId}/check`,
    { method: 'POST' },
  );
// The last persisted check result, so the board can show it again after a
// reload (the check itself is a POST; this is its GET counterpart).
export const getLastHypothesisCheck = (hypothesisId: string) =>
  apiFetch<{ hypothesis_id: string; log: HypothesisCheckLog | null }>(
    `/api/investigation/hypothesis/${hypothesisId}/check`,
  );
export const resolveHypothesis = (
  hypothesisId: string,
  body: { status: 'confirmed' | 'refuted'; resolved_reason: string },
) =>
  apiFetch<{ status: string; hypothesis: HypothesisRecord }>(
    `/api/investigation/hypothesis/${hypothesisId}/resolve`,
    { method: 'POST', body },
  );

// ─── misc ───────────────────────────────────────────────────────────────────
export const warmup = () =>
  apiFetch<{ status: string; dispatched: boolean }>('/api/warmup', { method: 'POST' }).catch(() => null);
export const transcribe = (audio: Blob, language: string) => {
  const fd = new FormData();
  fd.append('audio', audio, 'recording.wav');
  fd.append('language', language);
  return apiFetch<{ transcript: string }>('/api/transcribe', { method: 'POST', body: fd });
};

// Post-process a raw (browser or Zia) transcript into a clean investigative
// query — police-station names, IPC/BNS sections, code-mixed verbs. Best-effort
// server-side: returns the input unchanged on failure.
export const normalizeTranscript = (text: string, language: string) =>
  apiFetch<{ normalized_text: string; original_text: string }>('/api/transcribe/normalize', {
    method: 'POST',
    body: { text, language },
  });
