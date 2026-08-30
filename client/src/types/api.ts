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
