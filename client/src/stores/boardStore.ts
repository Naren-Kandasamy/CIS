import { create } from 'zustand';
import type { BoardCard, PinnedItem } from '../types/board';
import type { HypothesisRecord } from '../types/hypothesis';
import * as api from '../lib/api';

// Phase 4: per-case persistent board state. Two server docs back this:
//   • case_board:{id}        — append-only pin log  → pinsByCase
//   • case_board_layout:{id} — mutable card layout  → layoutByCase (used fully in Phase 5)
// plus case-scoped hypotheses (GET/POST /api/cases/:id/hypotheses) → hypothesesByCase.

interface PinInput {
  caseId: string;
  sourceSessionId: string;
  contentType: 'citation' | 'suspect' | 'fir' | string;
  content: Record<string, unknown>;
}

interface AddHypothesisInput {
  caseId: string;
  statement: string;
  linkedEntityIds?: string[];
  firId?: string | null;
}

interface BoardState {
  pinsByCase: Record<string, PinnedItem[]>;
  layoutByCase: Record<string, BoardCard[]>;
  hypothesesByCase: Record<string, HypothesisRecord[]>;
  loadingByCase: Record<string, boolean>;

  fetchBoard: (caseId: string) => Promise<PinnedItem[]>;
  fetchLayout: (caseId: string) => Promise<BoardCard[]>;
  fetchHypotheses: (caseId: string) => Promise<HypothesisRecord[]>;
  /** Parallel first-load of pins + layout + hypotheses for a case. */
  loadCase: (caseId: string) => Promise<void>;

  pin: (input: PinInput) => Promise<void>;
  putLayout: (caseId: string, cards: BoardCard[]) => Promise<void>;
  addHypothesis: (input: AddHypothesisInput) => Promise<HypothesisRecord>;
}

export const useBoardStore = create<BoardState>((set, get) => ({
  pinsByCase: {},
  layoutByCase: {},
  hypothesesByCase: {},
  loadingByCase: {},

  fetchBoard: async (caseId) => {
    const { board } = await api.getBoard(caseId);
    set((s) => ({ pinsByCase: { ...s.pinsByCase, [caseId]: board } }));
    return board;
  },

  fetchLayout: async (caseId) => {
    const { cards } = await api.getBoardLayout(caseId);
    set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: cards } }));
    return cards;
  },

  fetchHypotheses: async (caseId) => {
    const { hypotheses } = await api.listCaseHypotheses(caseId);
    set((s) => ({ hypothesesByCase: { ...s.hypothesesByCase, [caseId]: hypotheses } }));
    return hypotheses;
  },

  loadCase: async (caseId) => {
    set((s) => ({ loadingByCase: { ...s.loadingByCase, [caseId]: true } }));
    try {
      await Promise.all([
        get().fetchBoard(caseId).catch(() => {}),
        get().fetchLayout(caseId).catch(() => {}),
        get().fetchHypotheses(caseId).catch(() => {}),
      ]);
    } finally {
      set((s) => ({ loadingByCase: { ...s.loadingByCase, [caseId]: false } }));
    }
  },

  pin: async ({ caseId, sourceSessionId, contentType, content }) => {
    const optimistic: PinnedItem = {
      pinned_by: 'me',
      pinned_at: Date.now() / 1000,
      source_session_id: sourceSessionId,
      content_type: contentType,
      content,
    };
    const prev = get().pinsByCase[caseId] ?? [];
    set((s) => ({ pinsByCase: { ...s.pinsByCase, [caseId]: [...prev, optimistic] } }));
    try {
      await api.pinToBoard(caseId, {
        source_session_id: sourceSessionId,
        content_type: contentType,
        content,
      });
      // Re-read so pinned_by / pinned_at reflect the server record.
      await get().fetchBoard(caseId);
    } catch (err) {
      set((s) => ({ pinsByCase: { ...s.pinsByCase, [caseId]: prev } }));
      throw err;
    }
  },

  putLayout: async (caseId, cards) => {
    const prev = get().layoutByCase[caseId] ?? [];
    set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: cards } }));
    try {
      const { cards: saved } = await api.putBoardLayout(caseId, cards);
      set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: saved } }));
    } catch (err) {
      set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: prev } }));
      throw err;
    }
  },

  addHypothesis: async ({ caseId, statement, linkedEntityIds = [], firId }) => {
    const { hypothesis } = await api.createCaseHypothesis(caseId, {
      statement,
      linked_entity_ids: linkedEntityIds,
      fir_id: firId ?? null,
    });
    set((s) => ({
      hypothesesByCase: {
        ...s.hypothesesByCase,
        [caseId]: [hypothesis, ...(s.hypothesesByCase[caseId] ?? [])],
      },
    }));
    return hypothesis;
  },
}));
