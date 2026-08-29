import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MessagesSquare, LayoutGrid } from 'lucide-react';
import { useCasesStore } from '../stores/casesStore';
import { useBoardStore } from '../stores/boardStore';
import EmptyState from '../components/common/EmptyState';
import { CitationsTable } from '../components/workspace/CitationsTable';
import { KeySuspectsList } from '../components/workspace/KeySuspectsList';
import { HypothesisStrip } from '../components/workspace/HypothesisStrip';
import { WorkspaceGraphs } from '../components/workspace/WorkspaceGraphs';

// Phase 4: per-case workspace backed by PERSISTENT server state — the pin log
// (case_board:{id}), the card layout (case_board_layout:{id}, used in Phase 5)
// and case-scoped hypotheses. Previously this rendered DashboardPanel fed by
// nothing but the last query's in-memory visualization.

export default function CaseWorkspacePage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const cases = useCasesStore((s) => s.cases);
  const sessionsByCase = useCasesStore((s) => s.sessionsByCase);
  const fetchCases = useCasesStore((s) => s.fetchCases);
  const fetchSessions = useCasesStore((s) => s.fetchSessions);
  const createSession = useCasesStore((s) => s.createSession);

  const pins = useBoardStore((s) => (caseId ? s.pinsByCase[caseId] : undefined));
  const hypotheses = useBoardStore((s) => (caseId ? s.hypothesesByCase[caseId] : undefined));
  const loadCase = useBoardStore((s) => s.loadCase);

  const [busy, setBusy] = useState(false);
  const current = cases.find((c) => c.case_id === caseId);
  const sessions = caseId ? sessionsByCase[caseId] : undefined;

  useEffect(() => {
    if (!caseId) return;
    if (cases.length === 0) fetchCases().catch(() => {});
    if (!sessionsByCase[caseId]) fetchSessions(caseId).catch(() => {});
    loadCase(caseId).catch(() => {});
  }, [caseId, cases.length, sessionsByCase, fetchCases, fetchSessions, loadCase]);

  if (!caseId) return null;

  const startSession = async () => {
    setBusy(true);
    try {
      const meta = await createSession(caseId);
      navigate(`/cases/${caseId}/sessions/${meta.session_id}`);
    } finally {
      setBusy(false);
    }
  };

  const citations = (pins ?? []).filter((p) => p.content_type === 'citation');
  const suspects = (pins ?? []).filter((p) => p.content_type === 'suspect');
  const hyps = hypotheses ?? [];
  const nothingYet = citations.length === 0 && suspects.length === 0 && hyps.length === 0;

  return (
    <div className="workspace-page">
      <header className="workspace-head flex items-start justify-between gap-4">
        <div>
          <h1 className="stamp-font">{current?.title ?? 'Case workspace'}</h1>
          <p>
            {current?.crime_no ? `Crime ${current.crime_no}` : 'Case file'}
            {current?.district ? ` · ${current.district}` : ''}
          </p>
        </div>
        <button
          type="button"
          className="btn-ghost flex items-center gap-1.5 flex-shrink-0"
          onClick={() => navigate(`/cases/${caseId}/board`)}
        >
          <LayoutGrid size={14} /> Evidence board
        </button>
      </header>

      {sessions && sessions.length === 0 ? (
        <EmptyState
          icon={<MessagesSquare size={26} />}
          title="No sessions in this case yet"
          message="A session is a line of questioning. Start one to query the intelligence system for this case."
          action={
            <button type="button" className="btn-primary" onClick={startSession} disabled={busy}>
              {busy ? 'Starting…' : 'Start first session'}
            </button>
          }
        />
      ) : nothingYet ? (
        <EmptyState
          icon={<LayoutGrid size={26} />}
          title="Nothing pinned to this case yet"
          message="Open a session, run a query, and pin the FIRs and suspects that matter. They'll persist here and on the evidence board."
        />
      ) : (
        <>
          <HypothesisStrip caseId={caseId} hypotheses={hyps} />
          <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
            <div className="lg:col-span-2">
              <CitationsTable citations={citations} />
            </div>
            <KeySuspectsList suspects={suspects} />
          </div>
          <WorkspaceGraphs citations={citations} suspects={suspects} />
        </>
      )}
    </div>
  );
}
