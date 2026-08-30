// Investigative hypothesis model. Mirrors shared/hypothesis_models.py.
// Replaces the interface in components/dashboard/HypothesisWorkspace.tsx that
// was written with a bogus `str` / `str[]` pseudo-type and never type-checked.

export type HypothesisStatus = 'open' | 'confirmed' | 'refuted';

export interface HypothesisRecord {
  hypothesis_id: string;
  fir_id: string;
  /** Added in the redesign so hypotheses aggregate per case, not per FIR. */
  case_id?: string | null;
  officer_id: string;
  /** Short gist shown by default on the board. */
  statement: string;
  /** Full source text; revealed by "read full hypothesis". */
  detail?: string | null;
  linked_entity_ids: string[];
  status: HypothesisStatus;
  created_date: string;
  resolved_by?: string;
  resolved_reason?: string;
  resolved_date?: string;
}

export interface HypothesisCheckLog {
  check_id: string;
  hypothesis_id: string;
  checked_date: string;
  new_supporting_evidence_count: number;
  new_contradicting_evidence_count: number;
  notes: string;
}
