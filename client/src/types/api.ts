// Response envelopes for the CIS backend.

import type { Case, SessionMeta, HistoryTurn } from './case';
import type { HypothesisRecord } from './hypothesis';
import type { BoardCard, PinnedItem } from './board';

export interface CasesResponse {
  cases: Case[];
}
export interface SessionsResponse {
  sessions: SessionMeta[];
}
export interface SessionDetailResponse {
  meta: SessionMeta;
  history: HistoryTurn[];
}
export interface BoardResponse {
  board: PinnedItem[];
}
export interface BoardLayoutResponse {
  cards: BoardCard[];
  /** Card ids explicitly removed from the board despite their suspect/citation
   * still being pinned — kept out of the auto-materialized set on every load. */
  dismissed?: string[];
}
export interface HypothesesResponse {
  hypotheses: HypothesisRecord[];
}

export interface LoginResponse {
  token: string;
  username: string;
  role: string;
  display_name: string;
}
