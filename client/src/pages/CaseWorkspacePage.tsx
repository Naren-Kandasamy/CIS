import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { MessagesSquare } from 'lucide-react';
import { useCasesStore } from '../stores/casesStore';
import DashboardPanel from '../components/dashboard/DashboardPanel';
import EmptyState from '../components/common/EmptyState';

// Per-case workspace. Phase 1: shows the existing analytics panel (still fed by
// nothing until Phase 4 wires persistent board data) plus a first-session CTA.

export default function CaseWorkspacePage() {
  const { caseId } = useParams();
  const navigate = useNavigate();
  const cases = useCasesStore((s) => s.cases);
  const sessionsByCase = useCasesStore((s) => s.sessionsByCase);
  const fetchCases = useCasesStore((s) => s.fetchCases);
  const fetchSessions = useCasesStore((s) => s.fetchSessions);
  const createSession = useCasesStore((s) => s.createSession);

  const [busy, setBusy] = useState(false);
  const current = cases.find((c) => c.case_id === caseId);
  const sessions = caseId ? sessionsByCase[caseId] : undefined;

  useEffect(() => {
    if (!caseId) return;
    if (cases.length === 0) fetchCases().catch(() => {});
    if (!sessionsByCase[caseId]) fetchSessions(caseId).catch(() => {});
  }, [caseId, cases.length, sessionsByCase, fetchCases, fetchSessions]);

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

  return (
    <div className="workspace-page">
      <header className="workspace-head">
        <h1 className="stamp-font">{current?.title ?? 'Case workspace'}</h1>
        <p>
          {current?.crime_no ? `Crime ${current.crime_no}` : 'Case file'}
          {current?.district ? ` · ${current.district}` : ''}
        </p>
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
      ) : (
        <DashboardPanel />
      )}
    </div>
  );
}
