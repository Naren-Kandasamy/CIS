import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FolderPlus } from 'lucide-react';
import { useCasesStore } from '../stores/casesStore';
import CaseFolder from '../components/cases/CaseFolder';
import NewCaseDialog from '../components/cases/NewCaseDialog';
import ConfirmDialog from '../components/common/ConfirmDialog';
import EmptyState from '../components/common/EmptyState';

// The folder room. Post-login landing: a desk of manila case folders. Opening
// one plays the folder animation and routes into the case workspace.

export default function CasesIndexPage() {
  const navigate = useNavigate();
  const cases = useCasesStore((s) => s.cases);
  const loaded = useCasesStore((s) => s.loaded);
  const sessionsByCase = useCasesStore((s) => s.sessionsByCase);
  const fetchCases = useCasesStore((s) => s.fetchCases);
  const fetchSessions = useCasesStore((s) => s.fetchSessions);
  const createCase = useCasesStore((s) => s.createCase);
  const deleteCase = useCasesStore((s) => s.deleteCase);

  const [showNew, setShowNew] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<string | null>(null);

  useEffect(() => {
    fetchCases()
      .then((list) => {
        // warm the first few folders' sheet previews
        list.slice(0, 6).forEach((c) => {
          if (!sessionsByCase[c.case_id]) fetchSessions(c.case_id).catch(() => {});
        });
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="cases-room">
      <header className="cases-room-head">
        <div>
          <h1>Case files</h1>
          <p>Open a folder to work the case — sessions, citations and the evidence board live inside.</p>
        </div>
      </header>

      {loaded && cases.length === 0 ? (
        <EmptyState
          icon={<FolderPlus size={28} />}
          title="No cases yet"
          message="Open your first case file to start an investigation."
          action={
            <button type="button" className="btn-primary" onClick={() => setShowNew(true)}>
              Open a case file
            </button>
          }
        />
      ) : (
        <div className="cases-grid">
          {cases.map((c) => (
            <CaseFolder
              key={c.case_id}
              data={c}
              sessions={sessionsByCase[c.case_id]}
              onDelete={() => setPendingDelete(c.case_id)}
            />
          ))}

          <div
            className="case-folder case-folder--new"
            role="button"
            tabIndex={0}
            aria-label="Open a new case file"
            onClick={() => setShowNew(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setShowNew(true);
              }
            }}
          >
            <span className="folder-tab mono-font">NEW</span>
            <div className="folder-cover">
              <span className="folder-add-label">
                <span className="folder-add-plus">+</span>
                Open a case file
              </span>
            </div>
          </div>
        </div>
      )}

      <NewCaseDialog
        open={showNew}
        onCancel={() => setShowNew(false)}
        onSubmit={async (values) => {
          const created = await createCase(values);
          setShowNew(false);
          navigate(`/cases/${created.case_id}`);
        }}
      />
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete case file"
        message="This permanently deletes the case, its sessions and its board. This cannot be undone."
        confirmLabel="Delete case"
        destructive
        onConfirm={async () => {
          if (pendingDelete) await deleteCase(pendingDelete);
          setPendingDelete(null);
        }}
        onCancel={() => setPendingDelete(null)}
      />
    </div>
  );
}
