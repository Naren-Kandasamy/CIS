// Corkboard model. The board layout is a single mutable doc per case
// (case_board_layout:{case_id}), distinct from the append-only pin log
// (case_board:{case_id}).

export type BoardCardKind = 'hypothesis' | 'suspect' | 'fir' | 'note';

export interface BoardCard {
  /** Stable id. Hypothesis-backed cards use `hyp:<hypothesis_id>`. */
  id: string;
  kind: BoardCardKind;
  /** Domain id this card stands for (hypothesis_id, accused_id, fir_id) — null for a free note. */
  refId: string | null;
  x: number;
  y: number;
  w: number;
  h: number;
  /** Token name or hex for the card's pin / accent. */
  color: string;
  /** Small tilt in degrees for the pinned-paper look. */
  rotation?: number;
  /** Free-note body text. */
  text?: string;
  /** Ids of other cards this one is corded to. */
  connections: string[];
}

export interface BoardLayout {
  cards: BoardCard[];
  updated_at: number;
  updated_by: string;
}

/** One entry in the append-only pin log (GET /api/cases/:id/board). */
export interface PinnedItem {
  pinned_by: string;
  pinned_at: number;
  source_session_id: string;
  content_type: 'citation' | 'suspect' | 'fir' | string;
  content: Record<string, any>;
}
