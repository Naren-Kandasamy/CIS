// Case & session data model. Mirrors backend/api/routes/cases.py and
// backend/api/routes/sessions.py response shapes.

export type CaseStatus = 'open' | 'closed' | string;

export interface Case {
  case_id: string;
  title: string;
  crime_no: string | null;
  district: string | null;
  status: CaseStatus;
  created_by: string;
  created_at: number;
  collaborators: string[];
  last_activity_at: number;
}

export interface SessionMeta {
  session_id: string;
  case_id: string;
  created_by: string;
  created_at: number;
  title: string | null;
  last_activity_at: number;
}

/** One completed turn as returned by GET /api/sessions/:id -> { history: [...] } */
export interface HistoryTurn {
  q: string;
  a: string;
  evidence?: unknown[];
  visualization?: unknown;
}

export interface SessionDetail {
  meta: SessionMeta;
  history: HistoryTurn[];
}
