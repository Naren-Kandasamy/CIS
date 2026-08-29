import { create } from 'zustand';
import type { Case, SessionMeta } from '../types/case';
import * as api from '../lib/api';

// Cases + per-case sessions. Optimistic delete semantics preserved from the old
// App.tsx (remove locally first, refetch on failure).

interface CasesState {
  cases: Case[];
  sessionsByCase: Record<string, SessionMeta[]>;
  loaded: boolean;

  fetchCases: () => Promise<Case[]>;
  fetchSessions: (caseId: string) => Promise<SessionMeta[]>;
  createCase: (input: { title: string; crime_no?: string | null; district?: string | null }) => Promise<Case>;
  createSession: (caseId: string) => Promise<SessionMeta>;
  deleteCase: (caseId: string) => Promise<void>;
  deleteSession: (caseId: string, sessionId: string) => Promise<void>;
  /** Bump a case to the top of the list after activity (local only). */
  touchCase: (caseId: string) => void;
}

export const useCasesStore = create<CasesState>((set, get) => ({
  cases: [],
  sessionsByCase: {},
  loaded: false,

  fetchCases: async () => {
    const { cases } = await api.listCases();
    set({ cases, loaded: true });
    return cases;
  },

  fetchSessions: async (caseId) => {
    const { sessions } = await api.listSessions(caseId);
    set((s) => ({ sessionsByCase: { ...s.sessionsByCase, [caseId]: sessions } }));
    return sessions;
  },

  createCase: async (input) => {
    const created = await api.createCase(input);
    set((s) => ({ cases: [created, ...s.cases] }));
    return created;
  },

  createSession: async (caseId) => {
    const meta = await api.createSession(caseId);
    set((s) => ({
      sessionsByCase: {
        ...s.sessionsByCase,
        [caseId]: [meta, ...(s.sessionsByCase[caseId] ?? [])],
      },
    }));
    return meta;
  },

  deleteCase: async (caseId) => {
    const prev = get().cases;
    set((s) => ({ cases: s.cases.filter((c) => c.case_id !== caseId) }));
    try {
      await api.deleteCase(caseId);
    } catch (err) {
      set({ cases: prev });
      throw err;
    }
  },

  deleteSession: async (caseId, sessionId) => {
    const prev = get().sessionsByCase[caseId] ?? [];
    set((s) => ({
      sessionsByCase: {
        ...s.sessionsByCase,
        [caseId]: prev.filter((x) => x.session_id !== sessionId),
      },
    }));
    try {
      await api.deleteSession(sessionId);
    } catch (err) {
      set((s) => ({ sessionsByCase: { ...s.sessionsByCase, [caseId]: prev } }));
      throw err;
    }
  },

  touchCase: (caseId) =>
    set((s) => {
      const idx = s.cases.findIndex((c) => c.case_id === caseId);
      if (idx <= 0) return s;
      const next = s.cases.slice();
      const [c] = next.splice(idx, 1);
      next.unshift({ ...c, last_activity_at: Date.now() / 1000 });
      return { cases: next };
    }),
}));
