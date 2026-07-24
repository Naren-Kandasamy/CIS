import React, { useState, useEffect } from 'react';
import { Lightbulb, CheckCircle2, XCircle, RefreshCw, Plus, ShieldAlert } from 'lucide-react';

interface HypothesisRecord {
  hypothesis_id: str;
  fir_id: str;
  officer_id: str;
  statement: str;
  linked_entity_ids: str[];
  status: 'open' | 'confirmed' | 'refuted';
  created_date: str;
  resolved_by?: str;
  resolved_reason?: str;
  resolved_date?: str;
}

interface HypothesisWorkspaceProps {
  firId?: string;
}

export default function HypothesisWorkspace({ firId = 'DEFAULT_CASE' }: HypothesisWorkspaceProps) {
  const [hypotheses, setHypotheses] = useState<HypothesisRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [showAddForm, setShowAddForm] = useState(false);
  const [statement, setStatement] = useState('');
  const [entitiesInput, setEntitiesInput] = useState('');
  const [checkLogs, setCheckLogs] = useState<Record<string, any>>({});
  const [checkingId, setCheckingId] = useState<string | null>(null);
  const [resolveModalId, setResolveModalId] = useState<string | null>(null);
  const [resolveStatus, setResolveStatus] = useState<'confirmed' | 'refuted'>('confirmed');
  const [resolveReason, setResolveReason] = useState('');

  const fetchHypotheses = async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/investigation/hypothesis/${firId}`);
      if (res.ok) {
        const data = await res.json();
        setHypotheses(data.hypotheses || []);
      }
    } catch (err) {
      console.error('Failed to fetch hypotheses:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHypotheses();
  }, [firId]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!statement.trim()) return;

    const linked_entity_ids = entitiesInput
      .split(',')
      .map(s => s.trim())
      .filter(Boolean);

    try {
      const res = await fetch('/api/investigation/hypothesis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          fir_id: firId,
          statement,
          linked_entity_ids,
        }),
      });

      if (res.ok) {
        setStatement('');
        setEntitiesInput('');
        setShowAddForm(false);
        fetchHypotheses();
      }
    } catch (err) {
      console.error('Failed to create hypothesis:', err);
    }
  };

  const handleCheck = async (id: string) => {
    setCheckingId(id);
    try {
      const res = await fetch(`/api/investigation/hypothesis/${id}/check`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setCheckLogs(prev => ({ ...prev, [id]: data.log }));
      }
    } catch (err) {
      console.error('Failed to run hypothesis check:', err);
    } finally {
      setCheckingId(null);
    }
  };

  const handleResolveSubmit = async () => {
    if (!resolveModalId || !resolveReason.trim()) return;

    try {
      const res = await fetch(`/api/investigation/hypothesis/${resolveModalId}/resolve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          status: resolveStatus,
          resolved_reason: resolveReason,
        }),
      });

      if (res.ok) {
        setResolveModalId(null);
        setResolveReason('');
        fetchHypotheses();
      }
    } catch (err) {
      console.error('Failed to resolve hypothesis:', err);
    }
  };

  return (
    <div
      style={{
        background: 'var(--bg-secondary)',
        border: '1px solid var(--glass-border)',
        borderRadius: '4px',
        padding: '20px',
      }}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Lightbulb size={20} style={{ color: 'var(--accent-primary)' }} />
          <h3 className="stamp-font text-lg font-semibold" style={{ color: 'var(--text-primary)' }}>
            Investigative Hypothesis Workspace
          </h3>
        </div>
        <button
          onClick={() => setShowAddForm(p => !p)}
          className="flex items-center gap-1 text-xs font-semibold uppercase tracking-wider px-3 py-1.5 rounded transition-all cursor-pointer"
          style={{
            background: 'var(--accent-primary)',
            color: '#f4eeda',
            border: '1px solid var(--accent-primary)',
          }}
        >
          <Plus size={14} /> Log Theory
        </button>
      </div>

      {/* Log Form */}
      {showAddForm && (
        <form onSubmit={handleCreate} className="mb-6 p-4 rounded" style={{ background: 'var(--bg-tertiary)', border: '1px solid var(--paper-line)' }}>
          <div className="mb-3">
            <label className="block text-xs font-mono font-semibold uppercase mb-1" style={{ color: 'var(--text-secondary)' }}>
              Theory Statement
            </label>
            <textarea
              value={statement}
              onChange={e => setStatement(e.target.value)}
              placeholder="e.g. Suspect A and B operated with a specialized glass cutter matching Case 402/2023..."
              rows={2}
              required
              className="w-full text-sm p-2.5 rounded"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--glass-border)',
                color: 'var(--text-primary)',
                fontFamily: "'IBM Plex Mono', monospace",
              }}
            />
          </div>
          <div className="mb-4">
            <label className="block text-xs font-mono font-semibold uppercase mb-1" style={{ color: 'var(--text-secondary)' }}>
              Linked Entity / Case IDs (comma separated)
            </label>
            <input
              type="text"
              value={entitiesInput}
              onChange={e => setEntitiesInput(e.target.value)}
              placeholder="ACC_102, FIR_2024_01, CSH004"
              className="w-full text-sm p-2 rounded"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--glass-border)',
                color: 'var(--text-primary)',
                fontFamily: "'IBM Plex Mono', monospace",
              }}
            />
          </div>
          <div className="flex gap-2 justify-end">
            <button
              type="button"
              onClick={() => setShowAddForm(false)}
              className="text-xs px-3 py-1.5 rounded cursor-pointer"
              style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-primary)' }}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="text-xs font-semibold px-4 py-1.5 rounded cursor-pointer"
              style={{ background: 'var(--accent-secondary)', color: '#f4eeda' }}
            >
              Save Hypothesis
            </button>
          </div>
        </form>
      )}

      {/* List */}
      {loading ? (
        <p className="text-xs italic text-center py-4" style={{ color: 'var(--text-secondary)' }}>Loading theories...</p>
      ) : hypotheses.length === 0 ? (
        <div className="text-center py-6 text-xs" style={{ color: 'var(--text-secondary)' }}>
          No logged hypotheses for case <span className="font-mono font-bold">{firId}</span>. Click "Log Theory" above to add one.
        </div>
      ) : (
        <div className="space-y-3">
          {hypotheses.map(hyp => {
            const log = checkLogs[hyp.hypothesis_id];
            return (
              <div
                key={hyp.hypothesis_id}
                className="p-4 rounded border flex flex-col gap-2"
                style={{
                  background: 'var(--bg-primary)',
                  borderColor: hyp.status === 'confirmed' ? '#2f4a3c' : hyp.status === 'refuted' ? '#8a2a24' : 'var(--glass-border)',
                }}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2">
                    {hyp.status === 'confirmed' ? (
                      <CheckCircle2 size={16} className="text-emerald-700" />
                    ) : hyp.status === 'refuted' ? (
                      <XCircle size={16} className="text-red-700" />
                    ) : (
                      <ShieldAlert size={16} style={{ color: 'var(--accent-gold)' }} />
                    )}
                    <span className="font-mono text-xs uppercase font-semibold px-2 py-0.5 rounded" style={{ background: 'var(--bg-tertiary)' }}>
                      {hyp.status}
                    </span>
                    <span className="text-xs font-mono" style={{ color: 'var(--text-secondary)' }}>
                      Log Date: {hyp.created_date ? new Date(hyp.created_date).toLocaleDateString() : ''}
                    </span>
                  </div>

                  {hyp.status === 'open' && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleCheck(hyp.hypothesis_id)}
                        disabled={checkingId === hyp.hypothesis_id}
                        className="flex items-center gap-1 text-xs px-2.5 py-1 rounded border cursor-pointer hover:opacity-80"
                        style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--glass-border)', color: 'var(--text-primary)' }}
                      >
                        <RefreshCw size={12} className={checkingId === hyp.hypothesis_id ? 'animate-spin' : ''} /> Run Check
                      </button>
                      <button
                        onClick={() => { setResolveModalId(hyp.hypothesis_id); setResolveStatus('confirmed'); }}
                        className="text-xs px-2.5 py-1 rounded font-semibold cursor-pointer"
                        style={{ background: '#2f4a3c', color: '#f4eeda' }}
                      >
                        Confirm
                      </button>
                      <button
                        onClick={() => { setResolveModalId(hyp.hypothesis_id); setResolveStatus('refuted'); }}
                        className="text-xs px-2.5 py-1 rounded font-semibold cursor-pointer"
                        style={{ background: '#8a2a24', color: '#f4eeda' }}
                      >
                        Refute
                      </button>
                    </div>
                  )}
                </div>

                <p className="text-sm font-serif" style={{ color: 'var(--text-primary)' }}>"{hyp.statement}"</p>

                {hyp.linked_entity_ids.length > 0 && (
                  <div className="flex items-center gap-1.5 flex-wrap text-xs">
                    <span className="font-mono text-[10px] uppercase text-gray-500">Entities:</span>
                    {hyp.linked_entity_ids.map(id => (
                      <span key={id} className="font-mono text-[11px] px-1.5 py-0.5 rounded border" style={{ background: 'var(--bg-tertiary)', borderColor: 'var(--glass-border)' }}>
                        {id}
                      </span>
                    ))}
                  </div>
                )}

                {log && (
                  <div className="mt-2 p-2.5 rounded text-xs font-mono" style={{ background: 'var(--bg-tertiary)', borderLeft: '3px solid var(--accent-primary)' }}>
                    <div>📊 {log.notes}</div>
                    <div className="text-[10px] mt-0.5 text-gray-600">
                      Checked: {new Date(log.checked_date).toLocaleTimeString()}
                    </div>
                  </div>
                )}

                {hyp.status !== 'open' && (
                  <div className="mt-1 text-xs italic font-serif" style={{ color: 'var(--text-secondary)' }}>
                    Resolved by <b>{hyp.resolved_by}</b> ({hyp.resolved_date ? new Date(hyp.resolved_date).toLocaleDateString() : ''}): "{hyp.resolved_reason}"
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Resolution Modal */}
      {resolveModalId && (
        <div className="fixed inset-0 bg-black/40 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="w-full max-w-md p-5 rounded shadow-xl" style={{ background: 'var(--bg-secondary)', border: '1px solid var(--glass-border)' }}>
            <h4 className="stamp-font text-base mb-2" style={{ color: 'var(--text-primary)' }}>
              Resolve Theory ({resolveStatus.toUpperCase()})
            </h4>
            <p className="text-xs mb-3" style={{ color: 'var(--text-secondary)' }}>
              Enter official rationale for marking this theory as {resolveStatus}. This action will be logged in the case audit trail.
            </p>
            <textarea
              value={resolveReason}
              onChange={e => setResolveReason(e.target.value)}
              placeholder="Provide investigative evidence/rationale..."
              rows={3}
              required
              className="w-full text-sm p-2.5 rounded mb-4"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--glass-border)',
                color: 'var(--text-primary)',
                fontFamily: "'IBM Plex Mono', monospace",
              }}
            />
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setResolveModalId(null)}
                className="text-xs px-3 py-1.5 rounded cursor-pointer"
                style={{ background: 'transparent', border: '1px solid var(--glass-border)', color: 'var(--text-primary)' }}
              >
                Cancel
              </button>
              <button
                onClick={handleResolveSubmit}
                disabled={!resolveReason.trim()}
                className="text-xs font-semibold px-4 py-1.5 rounded cursor-pointer disabled:opacity-50"
                style={{
                  background: resolveStatus === 'confirmed' ? '#2f4a3c' : '#8a2a24',
                  color: '#f4eeda',
                }}
              >
                Submit Resolution
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
