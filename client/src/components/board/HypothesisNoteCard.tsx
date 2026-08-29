import { useState } from 'react';
import { Check, RefreshCw, X } from 'lucide-react';
import type { HypothesisCheckLog, HypothesisRecord } from '../../types/hypothesis';

// Index-card rendering of one hypothesis on the board. Status ribbon, statement,
// linked-entity chips (dashed = no card on the board yet, click to add one),
// and — while open — inline Run check / Confirm / Refute controls.

interface Props {
  hypothesis: HypothesisRecord;
  checkLog?: HypothesisCheckLog;
  busy: boolean;
  onCheck: (hypothesisId: string) => void;
  onResolve: (hypothesisId: string, status: 'confirmed' | 'refuted', reason: string) => void;
  entityHasCard: (entityId: string) => boolean;
  onAddCardForEntity: (entityId: string) => void;
}

export function HypothesisNoteCard({
  hypothesis,
  checkLog,
  busy,
  onCheck,
  onResolve,
  entityHasCard,
  onAddCardForEntity,
}: Props) {
  const [resolveMode, setResolveMode] = useState<'confirmed' | 'refuted' | null>(null);
  const [reason, setReason] = useState('');

  const isOpen = hypothesis.status === 'open';

  const submitResolve = () => {
    if (!resolveMode || !reason.trim() || busy) return;
    onResolve(hypothesis.hypothesis_id, resolveMode, reason.trim());
    setResolveMode(null);
    setReason('');
  };

  return (
    <div className="hyp-note">
      <span className={`hyp-note-ribbon ${hypothesis.status}`}>{hypothesis.status}</span>

      <div className="hyp-note-body">{hypothesis.statement}</div>

      {hypothesis.linked_entity_ids.length > 0 && (
        <div className="hyp-note-entities" data-no-drag>
          {hypothesis.linked_entity_ids.map((eid) => {
            const has = entityHasCard(eid);
            return (
              <button
                key={eid}
                type="button"
                className={`hyp-note-chip ${has ? '' : 'missing'}`}
                title={has ? 'On the board' : 'Add a card for this entity'}
                onClick={() => {
                  if (!has) onAddCardForEntity(eid);
                }}
              >
                {has ? '● ' : '+ '}
                {eid}
              </button>
            );
          })}
        </div>
      )}

      {checkLog && (
        <div className="hyp-note-log" data-no-drag>
          {checkLog.new_supporting_evidence_count} supporting ·{' '}
          {checkLog.new_contradicting_evidence_count} contradicting
          {checkLog.notes ? ` — ${checkLog.notes}` : ''}
        </div>
      )}

      {!isOpen && hypothesis.resolved_reason && (
        <div className="hyp-note-log" data-no-drag>
          Resolved by {hypothesis.resolved_by ?? 'officer'}: {hypothesis.resolved_reason}
        </div>
      )}

      {isOpen && resolveMode === null && (
        <div className="hyp-note-actions" data-no-drag>
          <button
            type="button"
            className="board-mini-btn"
            disabled={busy}
            onClick={() => onCheck(hypothesis.hypothesis_id)}
          >
            <RefreshCw size={11} className={busy ? 'animate-spin' : ''} /> Check
          </button>
          <button
            type="button"
            className="board-mini-btn primary"
            disabled={busy}
            onClick={() => setResolveMode('confirmed')}
          >
            <Check size={11} /> Confirm
          </button>
          <button
            type="button"
            className="board-mini-btn danger"
            disabled={busy}
            onClick={() => setResolveMode('refuted')}
          >
            <X size={11} /> Refute
          </button>
        </div>
      )}

      {isOpen && resolveMode !== null && (
        <div className="hyp-note-resolve" data-no-drag>
          <textarea
            placeholder={`Why is this ${resolveMode}? (logged to the case)`}
            value={reason}
            onChange={(e) => setReason(e.target.value)}
          />
          <div className="hyp-note-actions">
            <button
              type="button"
              className={`board-mini-btn ${resolveMode === 'confirmed' ? 'primary' : 'danger'}`}
              disabled={!reason.trim() || busy}
              onClick={submitResolve}
            >
              Save
            </button>
            <button
              type="button"
              className="board-mini-btn"
              onClick={() => {
                setResolveMode(null);
                setReason('');
              }}
            >
              Cancel
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
