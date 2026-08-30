import { useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Check, Lightbulb, X } from 'lucide-react';
import type { Message } from '../../types/chat';
import { useBoardStore } from '../../stores/boardStore';
import { collectLinkedEntities, extractAnalysis, extractCitedFirIds } from '../../lib/analysis';

// A one-click bridge from "I just queried and saw a pattern" to a real
// HypothesisRecord. Pre-fills the statement from the answer's Analytical
// Synthesis and the linked entities from the evidence FIRs / accused ids; the
// officer edits and commits it (never auto-created — a hypothesis carries
// officer accountability).

const MAX_STATEMENT = 2000; // backend cap
const MAX_ENTITIES = 60;

export function HypothesisSuggestion({ message }: { message: Message }) {
  const { caseId } = useParams();
  const addHypothesis = useBoardStore((s) => s.addHypothesis);

  const analysis = useMemo(() => extractAnalysis(message.content), [message.content]);
  const suggestedEntities = useMemo(() => {
    const fromEvidence = collectLinkedEntities(message.evidence);
    if (fromEvidence.length > 0) return fromEvidence;
    // Reloaded turn: no evidence array survived history — recover FIR ids from
    // the answer's own [FIR: …] citations instead.
    return extractCitedFirIds(message.content);
  }, [message.evidence, message.content]);

  const [open, setOpen] = useState(false);
  const [statement, setStatement] = useState('');
  const [entities, setEntities] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (done) {
    return (
      <p className="hyp-suggest-done">
        <Check size={12} /> Logged to Working Hypotheses.
      </p>
    );
  }

  // no case context, or nothing analytical to seed from
  if (!caseId || !analysis) return null;

  const start = () => {
    setStatement(analysis.slice(0, MAX_STATEMENT));
    setEntities(suggestedEntities.slice(0, MAX_ENTITIES));
    setError(null);
    setOpen(true);
  };

  const save = async () => {
    const text = statement.trim().slice(0, MAX_STATEMENT);
    if (!text || busy) return;
    setBusy(true);
    setError(null);
    try {
      await addHypothesis({ caseId, statement: text, linkedEntityIds: entities });
      setDone(true);
    } catch {
      setError('Could not save. Try again.');
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button type="button" className="hyp-suggest-trigger" onClick={start}>
        <Lightbulb size={13} /> Log this analysis as a hypothesis
      </button>
    );
  }

  return (
    <div className="hyp-suggest">
      <div className="hyp-suggest-head">
        <span>
          <Lightbulb size={13} /> New hypothesis from this analysis
        </span>
        <button type="button" onClick={() => setOpen(false)} aria-label="Discard">
          <X size={13} />
        </button>
      </div>

      <textarea
        className="hyp-suggest-text"
        value={statement}
        onChange={(e) => setStatement(e.target.value)}
        rows={4}
        placeholder="State the theory to test…"
      />

      {entities.length > 0 && (
        <div className="hyp-suggest-chips">
          <span className="hyp-suggest-chips-label">links</span>
          {entities.map((id) => (
            <span key={id} className="hyp-suggest-chip" title={id}>
              {id.length > 14 ? `${id.slice(0, 8)}…` : id}
              <button
                type="button"
                onClick={() => setEntities((v) => v.filter((x) => x !== id))}
                aria-label={`Remove ${id}`}
              >
                ×
              </button>
            </span>
          ))}
        </div>
      )}

      {error && <span className="hyp-suggest-err">{error}</span>}

      <div className="hyp-suggest-actions">
        <button
          type="button"
          className="btn-primary"
          onClick={save}
          disabled={!statement.trim() || busy}
        >
          {busy ? 'Saving…' : 'Log hypothesis'}
        </button>
        <button type="button" className="btn-ghost" onClick={() => setOpen(false)}>
          Cancel
        </button>
      </div>
    </div>
  );
}
