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
  detail?: string | null;
  linkedEntityIds?: string[];
  firId?: string | null;
}

interface BoardState {
  pinsByCase: Record<string, PinnedItem[]>;
  layoutByCase: Record<string, BoardCard[]>;
  /** Card ids explicitly dismissed from the board (see dismissCard). */
  dismissedByCase: Record<string, string[]>;
  hypothesesByCase: Record<string, HypothesisRecord[]>;
  loadingByCase: Record<string, boolean>;

  fetchBoard: (caseId: string) => Promise<PinnedItem[]>;
  fetchLayout: (caseId: string) => Promise<BoardCard[]>;
  fetchHypotheses: (caseId: string) => Promise<HypothesisRecord[]>;
  /** Parallel first-load of pins + layout + hypotheses for a case. */
  loadCase: (caseId: string) => Promise<void>;

  pin: (input: PinInput) => Promise<void>;
  /** Unpin one case_board entry (identified by its pinned_at timestamp).
   * Deliberately independent of the evidence board: a card already on the
   * board (fir/suspect) carries its own content snapshot and is untouched by
   * this — pinned/unpinned only changes whether it shows in the workspace's
   * Pinned Citations / Key Suspects lists. */
  unpin: (caseId: string, pinnedAt: number) => Promise<void>;
  putLayout: (caseId: string, cards: BoardCard[]) => Promise<void>;
  addHypothesis: (input: AddHypothesisInput) => Promise<HypothesisRecord>;

  // ── corkboard (Phase 5) — local layout edits + a debounced server flush ──
  /** Replace the whole local layout for a case (no network). */
  setLayout: (caseId: string, cards: BoardCard[]) => void;
  /** Insert a card, or replace the one with the same id, in the local layout. */
  upsertCard: (caseId: string, card: BoardCard) => void;
  /** Shallow-merge a patch into an existing local card (no-op if absent). */
  patchCard: (caseId: string, id: string, patch: Partial<BoardCard>) => void;
  /** Drop a card from the local layout. */
  removeCard: (caseId: string, id: string) => void;
  /** Remove a fir/suspect card from the board AND mark it dismissed, so it
   * doesn't get auto-recreated on the next load while its pin still stands. */
  dismissCard: (caseId: string, id: string) => void;
  /** Debounced PUT of the current local layout (drags are already applied). */
  persistLayout: (caseId: string, delayMs?: number) => void;
  /** Upsert a single hypothesis record into hypothesesByCase (after resolve). */
  applyHypothesis: (caseId: string, record: HypothesisRecord) => void;
}

// Debounce timers for persistLayout, keyed by case id — module-scoped so they
// survive re-renders and store recreation is not a concern (store is a singleton).
const _flushTimers: Record<string, ReturnType<typeof setTimeout>> = {};

export const useBoardStore = create<BoardState>((set, get) => ({
  pinsByCase: {},
  layoutByCase: {},
  dismissedByCase: {},
  hypothesesByCase: {},
  loadingByCase: {},

  fetchBoard: async (caseId) => {
    const { board } = await api.getBoard(caseId);
    set((s) => ({ pinsByCase: { ...s.pinsByCase, [caseId]: board } }));
    return board;
  },

  fetchLayout: async (caseId) => {
    const { cards, dismissed } = await api.getBoardLayout(caseId);
    set((s) => ({
      layoutByCase: { ...s.layoutByCase, [caseId]: cards },
      dismissedByCase: { ...s.dismissedByCase, [caseId]: dismissed ?? [] },
    }));
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

  unpin: async (caseId, pinnedAt) => {
    const prev = get().pinsByCase[caseId] ?? [];
    set((s) => ({
      pinsByCase: { ...s.pinsByCase, [caseId]: prev.filter((p) => p.pinned_at !== pinnedAt) },
    }));
    try {
      await api.unpinFromBoard(caseId, pinnedAt);
    } catch (err) {
      set((s) => ({ pinsByCase: { ...s.pinsByCase, [caseId]: prev } }));
      throw err;
    }
  },

  putLayout: async (caseId, cards) => {
    const prev = get().layoutByCase[caseId] ?? [];
    set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: cards } }));
    try {
      const { cards: saved } = await api.putBoardLayout(caseId, cards, get().dismissedByCase[caseId] ?? []);
      set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: saved } }));
    } catch (err) {
      set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: prev } }));
      throw err;
    }
  },

  addHypothesis: async ({ caseId, statement, detail, linkedEntityIds = [], firId }) => {
    const { hypothesis } = await api.createCaseHypothesis(caseId, {
      statement,
      detail: detail ?? null,
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

  setLayout: (caseId, cards) =>
    set((s) => ({ layoutByCase: { ...s.layoutByCase, [caseId]: cards } })),

  upsertCard: (caseId, card) =>
    set((s) => {
      const prev = s.layoutByCase[caseId] ?? [];
      const idx = prev.findIndex((c) => c.id === card.id);
      const next = idx === -1 ? [...prev, card] : prev.map((c) => (c.id === card.id ? card : c));
      return { layoutByCase: { ...s.layoutByCase, [caseId]: next } };
    }),

  patchCard: (caseId, id, patch) =>
    set((s) => {
      const prev = s.layoutByCase[caseId] ?? [];
      if (!prev.some((c) => c.id === id)) return {};
      return {
        layoutByCase: {
          ...s.layoutByCase,
          [caseId]: prev.map((c) => (c.id === id ? { ...c, ...patch } : c)),
        },
      };
    }),

  removeCard: (caseId, id) =>
    set((s) => ({
      layoutByCase: {
        ...s.layoutByCase,
        [caseId]: (s.layoutByCase[caseId] ?? []).filter((c) => c.id !== id),
      },
    })),

  dismissCard: (caseId, id) =>
    set((s) => ({
      layoutByCase: {
        ...s.layoutByCase,
        [caseId]: (s.layoutByCase[caseId] ?? []).filter((c) => c.id !== id),
      },
      dismissedByCase: {
        ...s.dismissedByCase,
        [caseId]: (s.dismissedByCase[caseId] ?? []).includes(id)
          ? s.dismissedByCase[caseId]
          : [...(s.dismissedByCase[caseId] ?? []), id],
      },
    })),

  persistLayout: (caseId, delayMs = 800) => {
    if (_flushTimers[caseId]) clearTimeout(_flushTimers[caseId]);
    _flushTimers[caseId] = setTimeout(() => {
      delete _flushTimers[caseId];
      const cards = get().layoutByCase[caseId] ?? [];
      const dismissed = get().dismissedByCase[caseId] ?? [];
      api
        .putBoardLayout(caseId, cards, dismissed)
        .then(({ cards: saved, dismissed: savedDismissed }) =>
          set((s) => ({
            layoutByCase: { ...s.layoutByCase, [caseId]: saved },
            dismissedByCase: { ...s.dismissedByCase, [caseId]: savedDismissed ?? dismissed },
          })),
        )
        .catch(() => {
          // Keep the local layout; the next drag/link retries the flush.
        });
    }, delayMs);
  },

  applyHypothesis: (caseId, record) =>
    set((s) => {
      const prev = s.hypothesesByCase[caseId] ?? [];
      const idx = prev.findIndex((h) => h.hypothesis_id === record.hypothesis_id);
      const next =
        idx === -1 ? [record, ...prev] : prev.map((h) => (h.hypothesis_id === record.hypothesis_id ? record : h));
      return { hypothesesByCase: { ...s.hypothesesByCase, [caseId]: next } };
    }),
}));

// ── derived board cards ────────────────────────────────────────────────────
// The server layout doc (case_board_layout) is authoritative for *placed* cards.
// Hypotheses and pins that have no layout entry yet are materialized here at a
// deterministic scatter position; once the user drags one it is written to the
// layout and this synthesis no longer applies to it.

const SCATTER_COLS = 4;

function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i += 1) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

// `seq` is the running count of *auto-placed* cards (never mixed with the
// index of user-placed layout cards), so every unplaced card lands in its own
// grid cell — the ±14px hash jitter is cosmetic and stays well inside the
// 300×280 cell pitch, so cards can never overlap on a hash collision.
// `originY` pushes the grid clear of any cards the user has already dragged.
function scatter(
  id: string,
  seq: number,
  originY = 80,
): { x: number; y: number; rotation: number } {
  const h = hashStr(id);
  const col = seq % SCATTER_COLS;
  const row = Math.floor(seq / SCATTER_COLS);
  return {
    x: 80 + col * 300 + ((h % 28) - 14),
    y: originY + row * 280 + (((h >> 6) % 28) - 14),
    rotation: ((h >> 12) % 9) - 4,
  };
}

export function deriveBoardCards(
  layout: BoardCard[] | undefined,
  hypotheses: HypothesisRecord[] | undefined,
  pins: PinnedItem[] | undefined,
  dismissed: string[] | undefined = [],
): BoardCard[] {
  const out: BoardCard[] = layout ? [...layout] : [];
  const ids = new Set(out.map((c) => c.id));
  const dismissedIds = new Set(dismissed);

  // Auto-placed cards get their own sequential grid, started below whatever the
  // user has already dragged onto the board so a fresh hypothesis/pin never
  // materializes underneath an existing card.
  let seq = 0;
  const originY =
    out.length > 0 ? Math.max(80, ...out.map((c) => c.y + c.h)) + 40 : 80;

  const push = (card: BoardCard) => {
    if (ids.has(card.id) || dismissedIds.has(card.id)) return;
    ids.add(card.id);
    out.push(card);
  };

  (hypotheses ?? []).forEach((h) => {
    const id = `hyp:${h.hypothesis_id}`;
    if (ids.has(id)) return;
    push({
      id,
      kind: 'hypothesis',
      refId: h.hypothesis_id,
      w: 250,
      h: 200,
      color: 'var(--pin-gold)',
      connections: [],
      ...scatter(id, seq++, originY),
    });
  });

  (pins ?? []).forEach((p) => {
    const c = p.content as Record<string, any>;
    if (p.content_type === 'citation') {
      const fir = String(c.fir_id ?? c.data?.crime_no ?? '').trim();
      if (!fir) return;
      const id = `fir:${fir}`;
      if (ids.has(id)) return;
      push({
        id,
        kind: 'fir',
        refId: fir,
        w: 220,
        h: 120,
        color: 'var(--pin-green)',
        connections: [],
        content: p.content,
        ...scatter(id, seq++, originY),
      });
    } else if (p.content_type === 'suspect') {
      const sid = String(c.id ?? c.label ?? c.name ?? '').trim();
      if (!sid) return;
      const id = `suspect:${sid}`;
      if (ids.has(id)) return;
      push({
        id,
        kind: 'suspect',
        refId: sid,
        w: 150,
        h: 175,
        color: 'var(--pin-blue)',
        connections: [],
        content: p.content,
        ...scatter(id, seq++, originY),
      });
    }
  });

  return out;
}
