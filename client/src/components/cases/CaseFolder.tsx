import { useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import type { Case, SessionMeta } from '../../types/case';

// A manila case folder. Rests flat; on activation it lifts and its cover swings
// open to reveal the session "files" inside, then routes into the case.
// prefers-reduced-motion: no lift/rotate, a quick fade handled by CSS + a short
// navigate delay.

const OPEN_MS = 420;
const REDUCED_MS = 90;

function caseNumber(c: Case): string {
  if (c.crime_no) return c.crime_no;
  return c.case_id.replace(/^c_/, '').slice(0, 4).toUpperCase();
}

function relativeTime(epochSeconds: number): string {
  const diff = Date.now() / 1000 - epochSeconds;
  if (diff < 60) return 'just now';
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

interface CaseFolderProps {
  data: Case;
  sessions?: SessionMeta[];
  onDelete: () => void;
}

export default function CaseFolder({ data, sessions, onDelete }: CaseFolderProps) {
  const navigate = useNavigate();
  const [opening, setOpening] = useState(false);

  const open = useCallback(() => {
    if (opening) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    setOpening(true);
    window.setTimeout(() => navigate(`/cases/${data.case_id}`), reduced ? REDUCED_MS : OPEN_MS);
  }, [opening, navigate, data.case_id]);

  const sheetLabels = (sessions ?? []).slice(0, 3);
  const sessionCount = sessions?.length ?? 0;

  return (
    <div
      className="case-folder"
      data-open={opening || undefined}
      role="button"
      tabIndex={0}
      aria-label={`Open case ${caseNumber(data)} — ${data.title}`}
      onClick={open}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          open();
        }
      }}
    >
      <span className="folder-tab mono-font">CASE {caseNumber(data)}</span>

      <div className="folder-sheets" aria-hidden={!opening}>
        {sheetLabels.length > 0 ? (
          sheetLabels.map((s, i) => (
            <span className="folder-sheet" style={{ ['--i' as string]: i }} key={s.session_id}>
              {s.title || `Session ${sessionCount - i}`}
            </span>
          ))
        ) : (
          <span className="folder-sheet" style={{ ['--i' as string]: 0 }}>
            No sessions yet
          </span>
        )}
      </div>

      <div className="folder-cover">
        <div className="folder-cover-body">
          <h3 className="folder-title">{data.title}</h3>
          <dl className="folder-meta mono-font">
            {data.district && (
              <div>
                <dt>District</dt>
                <dd>{data.district}</dd>
              </div>
            )}
            <div>
              <dt>Sessions</dt>
              <dd>{sessionCount}</dd>
            </div>
            <div>
              <dt>Active</dt>
              <dd>{relativeTime(data.last_activity_at)}</dd>
            </div>
          </dl>
        </div>
        <button
          type="button"
          className="folder-delete"
          aria-label={`Delete case ${data.title}`}
          title="Delete case"
          onClick={(e) => {
            e.stopPropagation();
            onDelete();
          }}
        >
          ✕
        </button>
      </div>
    </div>
  );
}
