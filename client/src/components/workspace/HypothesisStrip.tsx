import { useState } from 'react';
import { Lightbulb, Plus } from 'lucide-react';
import type { HypothesisRecord } from '../../types/hypothesis';
import { useBoardStore } from '../../stores/boardStore';

// The workspace list is the "full read" surface: gist by default, with an
// opt-in expand to the stored source text (`detail`). Legacy records have no
// `detail`; if their own statement is long, still let it expand.
function HypothesisBody({ h }: { h: HypothesisRecord }) {
  const [open, setOpen] = useState(false);
  const full = (h.detail ?? '').trim();
  const hasFull = !!full && full !== h.statement.trim();
  const longStmt =
    !hasFull && (h.statement.length > 240 || h.statement.includes('\n'));
  const canExpand = hasFull || longStmt;
  const text = open && hasFull ? full : h.statement;

  return (
    <>
      <p
        className="text-sm"
        style={{
          color: 'var(--text-primary)',
          whiteSpace: 'pre-wrap',
          ...(canExpand && !open
            ? {
                display: '-webkit-box',
                WebkitLineClamp: 3,
                WebkitBoxOrient: 'vertical' as const,
                overflow: 'hidden',
              }
            : {}),
        }}
      >
        {text}
      </p>
      {canExpand && (
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="dossier-mono text-[11px] mt-1 font-bold"
          style={{
            color: 'var(--accent-primary)',
            background: 'none',
            border: 'none',
            padding: 0,
            cursor: 'pointer',
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
          }}
        >
          {open ? '▴ Show summary' : '▾ Read full hypothesis'}
        </button>
      )}
    </>
  );
}

// Phase 4: read-mostly hypotheses summary for the case. Full editing / checking
// / the corkboard lives in Phase 5; here we list them and allow a quick add.

const STATUS_STYLE: Record<string, string> = {
  open: 'text-amber-800 bg-amber-100 border-amber-300',
  confirmed: 'text-emerald-800 bg-emerald-100 border-emerald-300',
  refuted: 'text-rose-800 bg-rose-100 border-rose-300',
};

export function HypothesisStrip({
  caseId,
  hypotheses,
}: {
  caseId: string;
  hypotheses: HypothesisRecord[];
}) {
  const addHypothesis = useBoardStore((s) => s.addHypothesis);
  const [adding, setAdding] = useState(false);
  const [statement, setStatement] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!statement.trim() || busy) return;
    setBusy(true);
    setError(null);
    try {
      await addHypothesis({ caseId, statement: statement.trim() });
      setStatement('');
      setAdding(false);
    } catch {
      setError('Could not save hypothesis.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dossier-panel dossier-paperclip" style={{ padding: '20px' }}>
      <div className="flex items-center justify-between mb-1">
        <h3 className="dossier-panel-title text-base flex items-center gap-2">
          <Lightbulb size={15} style={{ color: 'var(--accent-gold)' }} /> Working Hypotheses
        </h3>
        <button
          type="button"
          className="btn-ghost flex items-center gap-1"
          onClick={() => setAdding((v) => !v)}
        >
          <Plus size={13} /> New
        </button>
      </div>
      <p className="dossier-panel-subtitle text-xs mb-4">
        {hypotheses.length} recorded · checked and corded on the evidence board.
      </p>

      {adding && (
        <div className="flex flex-col gap-2 mb-4">
          <textarea
            className="w-full text-sm p-2 rounded-sm"
            style={{
              border: '1px solid var(--paper-line)',
              background: 'var(--bg-primary)',
              minHeight: '64px',
              resize: 'vertical',
            }}
            placeholder="State a theory to test against the graph…"
            value={statement}
            onChange={(e) => setStatement(e.target.value)}
          />
          {error && (
            <span className="text-xs" style={{ color: 'var(--accent-primary)' }}>
              {error}
            </span>
          )}
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-primary"
              onClick={submit}
              disabled={!statement.trim() || busy}
            >
              {busy ? 'Saving…' : 'Save hypothesis'}
            </button>
            <button type="button" className="btn-ghost" onClick={() => setAdding(false)}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {hypotheses.length === 0 ? (
        <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
          No hypotheses yet.
        </p>
      ) : (
        <ul className="flex flex-col gap-2">
          {hypotheses.map((h) => (
            <li
              key={h.hypothesis_id}
              className="flex items-start gap-3 py-2"
              style={{ borderTop: '1px dashed var(--paper-line)' }}
            >
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider font-semibold whitespace-nowrap mt-0.5 ${
                  STATUS_STYLE[h.status] ?? STATUS_STYLE.open
                }`}
              >
                {h.status}
              </span>
              <div className="min-w-0">
                <HypothesisBody h={h} />
                {h.linked_entity_ids.length > 0 && (
                  <p className="dossier-mono text-[11px] mt-0.5">
                    linked: {h.linked_entity_ids.join(', ')}
                  </p>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
