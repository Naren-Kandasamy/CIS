import { useEffect, useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';
import {
  Shield,
  FolderOpen,
  LayoutDashboard,
  Layers,
  MessageSquarePlus,
  LogOut,
  Trash2,
  Plus,
} from 'lucide-react';
import { useAuthStore } from '../../stores/authStore';
import { useCasesStore } from '../../stores/casesStore';
import NewCaseDialog from '../cases/NewCaseDialog';
import ConfirmDialog from '../common/ConfirmDialog';

// The spine of the case folder: brand, a link back to the folder room, and —
// when a case is open — its sessions plus Workspace / Board links.

export default function CaseDrawerSidebar() {
  const navigate = useNavigate();
  const { caseId, sessionId } = useParams();
  const displayName = useAuthStore((s) => s.displayName);
  const logout = useAuthStore((s) => s.logout);

  const cases = useCasesStore((s) => s.cases);
  const sessionsByCase = useCasesStore((s) => s.sessionsByCase);
  const fetchSessions = useCasesStore((s) => s.fetchSessions);
  const createCase = useCasesStore((s) => s.createCase);
  const createSession = useCasesStore((s) => s.createSession);
  const deleteSession = useCasesStore((s) => s.deleteSession);

  const [showNewCase, setShowNewCase] = useState(false);
  const [pendingSessionDelete, setPendingSessionDelete] = useState<string | null>(null);
  const [creatingSession, setCreatingSession] = useState(false);

  const activeCase = cases.find((c) => c.case_id === caseId);
  const sessions = caseId ? sessionsByCase[caseId] ?? [] : [];

  useEffect(() => {
    if (caseId && !sessionsByCase[caseId]) fetchSessions(caseId).catch(() => {});
  }, [caseId, sessionsByCase, fetchSessions]);

  const onNewSession = async () => {
    if (!caseId || creatingSession) return;
    setCreatingSession(true);
    try {
      const meta = await createSession(caseId);
      navigate(`/cases/${caseId}/sessions/${meta.session_id}`);
    } finally {
      setCreatingSession(false);
    }
  };

  const onConfirmSessionDelete = async () => {
    if (!caseId || !pendingSessionDelete) return;
    const wasActive = pendingSessionDelete === sessionId;
    await deleteSession(caseId, pendingSessionDelete);
    setPendingSessionDelete(null);
    if (wasActive) navigate(`/cases/${caseId}`);
  };

  return (
    <aside className="sidebar" aria-label="Case navigation">
      <header className="brand">
        <div className="brand-icon">
          <Shield color="var(--accent-primary)" size={20} />
        </div>
        <h1>
          PS-1 <span>CIS</span>
        </h1>
      </header>

      <nav className="drawer-nav" aria-label="Primary">
        <NavLink to="/cases" className="drawer-link" end>
          <FolderOpen size={17} /> All cases
        </NavLink>
        <button type="button" className="drawer-link drawer-link--action" onClick={() => setShowNewCase(true)}>
          <Plus size={17} /> New case
        </button>

        {activeCase && (
          <div className="drawer-case">
            <div className="drawer-case-title mono-font" title={activeCase.title}>
              {activeCase.title}
            </div>

            <NavLink to={`/cases/${activeCase.case_id}`} end className="drawer-sublink">
              <LayoutDashboard size={15} /> Workspace
            </NavLink>
            <NavLink to={`/cases/${activeCase.case_id}/board`} className="drawer-sublink">
              <Layers size={15} /> Evidence board
            </NavLink>

            <div className="drawer-sessions-head">
              <span>Sessions</span>
              <button
                type="button"
                onClick={onNewSession}
                disabled={creatingSession}
                aria-label="New session"
                title="New session"
              >
                <MessageSquarePlus size={14} />
              </button>
            </div>

            <div className="drawer-sessions">
              {sessions.length === 0 && (
                <p className="drawer-sessions-empty">No sessions yet.</p>
              )}
              {sessions.map((s) => (
                <div key={s.session_id} className="drawer-session-row">
                  <NavLink
                    to={`/cases/${activeCase.case_id}/sessions/${s.session_id}`}
                    className="drawer-session-link"
                  >
                    {s.title || 'New session…'}
                  </NavLink>
                  <button
                    type="button"
                    className="drawer-session-del"
                    onClick={() => setPendingSessionDelete(s.session_id)}
                    aria-label={`Delete session ${s.title ?? ''}`}
                    title="Delete session"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </nav>

      <footer className="drawer-footer">
        {displayName && (
          <div className="drawer-user">
            Signed in as <strong>{displayName}</strong>
          </div>
        )}
        <button
          type="button"
          className="drawer-link"
          onClick={() => {
            logout();
            navigate('/login');
          }}
        >
          <LogOut size={17} /> Sign out
        </button>
      </footer>

      <NewCaseDialog
        open={showNewCase}
        onCancel={() => setShowNewCase(false)}
        onSubmit={async (values) => {
          const created = await createCase(values);
          setShowNewCase(false);
          navigate(`/cases/${created.case_id}`);
        }}
      />
      <ConfirmDialog
        open={pendingSessionDelete !== null}
        title="Delete session"
        message="This removes the session and its chat history. This cannot be undone."
        confirmLabel="Delete"
        destructive
        onConfirm={onConfirmSessionDelete}
        onCancel={() => setPendingSessionDelete(null)}
      />
    </aside>
  );
}
