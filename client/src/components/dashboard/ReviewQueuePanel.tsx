import React, { useState, useEffect, useCallback } from 'react';
import { AlertTriangle, CheckCircle, XCircle, RefreshCw, FileSearch } from 'lucide-react';

interface ReviewQueueItem {
  item_id: string;
  item_type: 'cold_case_match' | 'contradiction_alert' | 'anpr_wanted_hit' | 'interstate_handoff';
  fir_id: string;
  related_fir_id?: string;
  accused_id?: string;
  summary: string;
  score?: number;
  created_date: string;
  status: string;
  reviewed_by?: string;
  reviewed_date?: string;
}

interface ReviewQueuePanelProps {
  authToken: string | null;
  onOpenFir?: (firId: string) => void;
}

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  cold_case_match:    { label: 'COLD CASE MATCH', color: 'var(--accent-primary)' },
  contradiction_alert: { label: 'CONTRADICTION', color: 'var(--accent-gold)' },
  anpr_wanted_hit:    { label: 'ANPR HIT',        color: '#2f4a3c' },
  interstate_handoff: { label: 'INTERSTATE',       color: '#4a5a7a' },
};

function ScoreBadge({ score }: { score?: number }) {
  if (score == null) return null;
  const pct = Math.round(score * 100);
  const color = score >= 0.85 ? 'var(--accent-primary)' : score >= 0.75 ? 'var(--accent-gold)' : 'var(--text-tertiary)';
  return (
    <span style={{
      fontFamily: 'IBM Plex Mono, monospace',
      fontSize: '0.7rem',
      fontWeight: 600,
      color,
      background: 'var(--bg-tertiary)',
      borderRadius: 'var(--radius)',
      padding: '2px 8px',
      border: `1px solid ${color}44`,
      letterSpacing: '0.05em',
    }}>
      {pct}% MATCH
    </span>
  );
}

function AlertCard({
  item,
  onResolve,
  onDismiss,
  onOpenFir,
  resolving,
}: {
  item: ReviewQueueItem;
  onResolve: (id: string) => void;
  onDismiss: (id: string) => void;
  onOpenFir?: (id: string) => void;
  resolving: string | null;
}) {
  const typeInfo = TYPE_LABELS[item.item_type] ?? { label: item.item_type.toUpperCase(), color: 'var(--text-secondary)' };
  const isLoading = resolving === item.item_id;

  return (
    <div
      className="dossier-panel dossier-paperclip"
      style={{
        padding: '16px',
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        position: 'relative',
        transition: 'opacity 0.3s ease',
        opacity: isLoading ? 0.5 : 1,
      }}
    >
      {/* Type stamp + score */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <span
          className="stamp-font"
          style={{
            color: typeInfo.color,
            fontSize: '0.7rem',
            letterSpacing: '0.12em',
            transform: 'rotate(-1.5deg)',
            display: 'inline-block',
          }}
        >
          ⬛ {typeInfo.label}
        </span>
        <ScoreBadge score={item.score} />
      </div>

      {/* Summary */}
      <p style={{ fontSize: '0.82rem', color: 'var(--text-primary)', lineHeight: 1.5, margin: 0 }}>
        {item.summary}
      </p>

      {/* Case IDs */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
        <span className="dossier-mono" style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>
          NEW: <strong style={{ color: 'var(--text-primary)' }}>{item.fir_id}</strong>
        </span>
        {item.related_fir_id && (
          <span className="dossier-mono" style={{ fontSize: '0.68rem', color: 'var(--text-secondary)' }}>
            {'→'} COLD: <strong style={{ color: 'var(--text-primary)' }}>{item.related_fir_id}</strong>
          </span>
        )}
        {item.accused_id && (
          <span className="dossier-mono" style={{ fontSize: '0.68rem', color: 'var(--text-tertiary)' }}>
            ACC: {item.accused_id}
          </span>
        )}
      </div>

      {/* Date */}
      <div style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', fontFamily: 'IBM Plex Mono, monospace' }}>
        Flagged: {new Date(item.created_date).toLocaleString()}
      </div>

      {/* Actions */}
      <div
        style={{
          display: 'flex',
          gap: '8px',
          paddingTop: '8px',
          borderTop: '1px dashed var(--paper-line)',
          flexWrap: 'wrap',
        }}
      >
        {item.related_fir_id && onOpenFir && (
          <button
            type="button"
            onClick={() => onOpenFir(item.related_fir_id!)}
            disabled={isLoading}
            style={{
              flex: 1,
              minWidth: '100px',
              padding: '6px 10px',
              background: 'var(--bg-tertiary)',
              border: '1px solid var(--glass-border)',
              borderRadius: 'var(--radius)',
              color: 'var(--text-secondary)',
              fontSize: '0.7rem',
              fontFamily: 'IBM Plex Mono, monospace',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              justifyContent: 'center',
            }}
          >
            <FileSearch size={12} /> Open File
          </button>
        )}
        <button
          type="button"
          onClick={() => onResolve(item.item_id)}
          disabled={isLoading}
          style={{
            flex: 1,
            minWidth: '100px',
            padding: '6px 10px',
            background: isLoading ? 'var(--bg-tertiary)' : 'transparent',
            border: '1px solid rgba(47, 74, 60, 0.5)',
            borderRadius: 'var(--radius)',
            color: '#2f4a3c',
            fontSize: '0.7rem',
            fontFamily: 'IBM Plex Mono, monospace',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            justifyContent: 'center',
          }}
        >
          <CheckCircle size={12} /> Reviewed
        </button>
        <button
          type="button"
          onClick={() => onDismiss(item.item_id)}
          disabled={isLoading}
          style={{
            flex: 1,
            minWidth: '100px',
            padding: '6px 10px',
            background: 'transparent',
            border: '1px solid rgba(138, 42, 36, 0.4)',
            borderRadius: 'var(--radius)',
            color: 'var(--accent-primary)',
            fontSize: '0.7rem',
            fontFamily: 'IBM Plex Mono, monospace',
            cursor: isLoading ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            justifyContent: 'center',
          }}
        >
          <XCircle size={12} /> Dismiss
        </button>
      </div>
    </div>
  );
}

export default function ReviewQueuePanel({ authToken, onOpenFir }: ReviewQueuePanelProps) {
  const [items, setItems] = useState<ReviewQueueItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [resolving, setResolving] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchQueue = useCallback(async () => {
    if (!authToken) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/api/review-queue`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data: ReviewQueueItem[] = await res.json();
      setItems(data);
    } catch (err: any) {
      setError(`Failed to load alerts: ${err.message}`);
    } finally {
      setLoading(false);
    }
  }, [authToken]);

  useEffect(() => { fetchQueue(); }, [fetchQueue]);

  const handleResolve = async (itemId: string, status: 'reviewed' | 'dismissed') => {
    if (!authToken) return;
    setResolving(itemId);
    try {
      const res = await fetch(
        `${import.meta.env.VITE_API_BASE_URL || ''}/api/review-queue/${itemId}/resolve`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${authToken}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ status }),
        }
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      // Optimistically remove from local list
      setItems(prev => prev.filter(i => i.item_id !== itemId));
    } catch (err: any) {
      setError(`Failed to update item: ${err.message}`);
    } finally {
      setResolving(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', height: '100%' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '12px', borderBottom: '1px dashed var(--glass-border)' }}>
        <div>
          <h3 className="dossier-panel-title" style={{ fontSize: '1rem', marginBottom: '2px' }}>
            Proactive Alerts
          </h3>
          <p className="dossier-panel-subtitle" style={{ fontSize: '0.75rem' }}>
            Cold case matches, contradictions, and system-generated flags awaiting review.
          </p>
        </div>
        <button
          type="button"
          onClick={fetchQueue}
          disabled={loading}
          aria-label="Refresh alerts"
          style={{
            background: 'transparent',
            border: '1px solid var(--glass-border)',
            borderRadius: 'var(--radius)',
            padding: '6px 10px',
            cursor: loading ? 'not-allowed' : 'pointer',
            color: 'var(--text-secondary)',
            display: 'flex',
            alignItems: 'center',
            gap: '4px',
            fontSize: '0.7rem',
            fontFamily: 'IBM Plex Mono, monospace',
          }}
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {/* Error */}
      {error && (
        <div style={{ background: 'rgba(138, 42, 36, 0.08)', border: '1px solid rgba(138, 42, 36, 0.3)', borderRadius: 'var(--radius)', padding: '10px 14px', color: 'var(--accent-primary)', fontSize: '0.78rem', display: 'flex', gap: '8px', alignItems: 'center' }}>
          <AlertTriangle size={14} /> {error}
        </div>
      )}

      {/* Alert list or empty state */}
      {!loading && items.length === 0 && !error ? (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '12px', color: 'var(--text-tertiary)', paddingTop: '40px' }}>
          <CheckCircle size={36} strokeWidth={1.2} />
          <span className="stamp-font" style={{ fontSize: '0.9rem', letterSpacing: '0.08em' }}>NO PENDING ALERTS</span>
          <span style={{ fontSize: '0.72rem' }}>All flagged items have been reviewed.</span>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '14px', overflowY: 'auto' }}>
          {items.map(item => (
            <AlertCard
              key={item.item_id}
              item={item}
              resolving={resolving}
              onResolve={(id) => handleResolve(id, 'reviewed')}
              onDismiss={(id) => handleResolve(id, 'dismissed')}
              onOpenFir={onOpenFir}
            />
          ))}
        </div>
      )}

      {/* Footer count */}
      {items.length > 0 && (
        <div style={{ fontSize: '0.65rem', color: 'var(--text-tertiary)', fontFamily: 'IBM Plex Mono, monospace', textAlign: 'right', paddingTop: '8px', borderTop: '1px dashed var(--paper-line)' }}>
          {items.length} alert{items.length !== 1 ? 's' : ''} pending review
        </div>
      )}
    </div>
  );
}
