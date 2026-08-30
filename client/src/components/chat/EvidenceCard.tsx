import { useState, type MouseEvent } from 'react';
import { useParams } from 'react-router-dom';
import { Pin } from 'lucide-react';
import type { Message } from '../../types/chat';
import type { SelectedEntity } from '../../types/entities';
import type { FeedbackVerdict } from '../../stores/chatStore';
import { useBoardStore } from '../../stores/boardStore';
import { firLabel } from '../../lib/utils';
import { FeedbackControls } from './FeedbackControls';

// Phase 3: a single retrieved-evidence citation card, extracted verbatim from
// SessionChatPage's evidence grid (originally App.tsx:842-969).

type EvidenceItem = NonNullable<Message['evidence']>[number];

interface EvidenceCardProps {
  item: EvidenceItem;
  idx: number;
  openEntity: (entity: SelectedEntity) => void;
  recorded?: { verdict: FeedbackVerdict };
  isCorrectionOpen: boolean;
  explanation: string;
  onExplanationChange: (value: string) => void;
  onOpenCorrection: () => void;
  onCancelCorrection: () => void;
  onSubmitFeedback: (item: EvidenceItem, verdict: 'confirmed' | 'corrected', explanation?: string) => void;
}

export function EvidenceCard({
  item,
  idx,
  openEntity,
  recorded,
  isCorrectionOpen,
  explanation,
  onExplanationChange,
  onOpenCorrection,
  onCancelCorrection,
  onSubmitFeedback,
}: EvidenceCardProps) {
  const { caseId, sessionId } = useParams();
  const pin = useBoardStore((s) => s.pin);
  const casePins = useBoardStore((s) => (caseId ? s.pinsByCase[caseId] : undefined));
  const [pinBusy, setPinBusy] = useState(false);

  const alreadyPinned = !!casePins?.some(
    (p) =>
      p.content_type === 'citation' &&
      ((p.content as Record<string, unknown>).fir_id ?? null) === (item.fir_id ?? null) &&
      item.fir_id != null,
  );

  const pinThis = async (e: MouseEvent) => {
    e.stopPropagation();
    if (!caseId || !sessionId || alreadyPinned || pinBusy) return;
    setPinBusy(true);
    try {
      await pin({
        caseId,
        sourceSessionId: sessionId,
        contentType: 'citation',
        content: {
          fir_id: item.fir_id,
          confidence: item.confidence,
          crime_type: item.crime_type ?? item.data?.crime_type,
          data: item.data ?? {},
        },
      });
    } catch {
      /* leave un-pinned; store already rolled back */
    } finally {
      setPinBusy(false);
    }
  };

  const accusedIds: string[] = Array.isArray(item.data?.accused_ids)
    ? (item.data!.accused_ids as unknown[]).map(String).filter(Boolean)
    : [];

  const openAccused = (e: MouseEvent, accusedId: string) => {
    e.stopPropagation();
    openEntity({
      type: 'person',
      id: accusedId,
      label: accusedId,
      data: { id: accusedId, accused_ids: accusedIds },
      evidenceItems: [item],
      linkedNodes: [],
    });
  };

  const confidenceTier = String(item.confidence ?? '').toLowerCase();
  const confidenceColor =
    confidenceTier === 'high'
      ? 'text-emerald-800 bg-emerald-100 border-emerald-300'
      : confidenceTier === 'medium'
        ? 'text-amber-800 bg-amber-100 border-amber-300'
        : 'text-rose-800 bg-rose-100 border-rose-300';
  const firTitle = firLabel(item.data?.crime_no as string | undefined, item.fir_id);
  const openThis = () =>
    openEntity({
      type: 'fir',
      id: item.fir_id ?? `evidence-${idx}`,
      label: firTitle,
      data: item.data ?? {},
      evidenceItems: [item],
    });

  return (
    <div
      className="evidence-item p-3 rounded-sm flex flex-col gap-2 entity-clickable"
      style={{ border: '1px solid var(--paper-line)', background: 'var(--bg-primary)', cursor: 'pointer' }}
      onClick={openThis}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') openThis();
      }}
      aria-label={`View details for ${firTitle}`}
    >
      <div
        className="flex items-center justify-between pb-2"
        style={{ borderBottom: '1px dashed var(--paper-line)' }}
      >
        <div className="font-mono font-medium text-sm truncate" style={{ color: 'var(--text-primary)' }}>
          {firTitle}
        </div>
        <div className="flex items-center gap-1.5 flex-shrink-0">
          {item.confidence && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider font-semibold whitespace-nowrap ${confidenceColor}`}
            >
              {item.confidence}
            </span>
          )}
          {caseId && sessionId && item.fir_id && (
            <button
              type="button"
              onClick={pinThis}
              disabled={alreadyPinned || pinBusy}
              aria-label={alreadyPinned ? 'Pinned to case board' : 'Pin this FIR to the case board'}
              title={alreadyPinned ? 'Pinned to case board' : 'Pin this FIR to the case board'}
              className={`evidence-pin-btn${alreadyPinned ? ' is-pinned' : ''}`}
              style={{ opacity: pinBusy ? 0.5 : 1 }}
            >
              <Pin size={15} fill={alreadyPinned ? 'currentColor' : 'none'} />
              <span>{alreadyPinned ? 'Pinned' : pinBusy ? 'Pinning…' : 'Pin'}</span>
            </button>
          )}
        </div>
      </div>
      <div className="text-xs space-y-1" style={{ color: 'var(--text-secondary)' }}>
        {item.data?.crime_type && (
          <div>
            <strong>Type:</strong> {item.data.crime_type}
          </div>
        )}
        {item.data?.district && (
          <div>
            <strong>District:</strong> {item.data.district}
          </div>
        )}
        {item.data?.Date && (
          <div>
            <strong>Date:</strong> {item.data.Date}
          </div>
        )}
        {item.data?.weapon && (
          <div>
            <strong>Weapon:</strong> {item.data.weapon}
          </div>
        )}
        <div
          className="text-[11px] mt-1.5 font-semibold"
          style={{ color: 'var(--accent-secondary)', fontFamily: 'IBM Plex Mono, monospace' }}
        >
          Click card to expand full details →
        </div>
      </div>

      {accusedIds.length > 0 && (
        <div className="evidence-accused-row">
          <span className="evidence-accused-label">Accused</span>
          {accusedIds.map((aid) => (
            <button
              key={aid}
              type="button"
              className="evidence-accused-chip"
              onClick={(e) => openAccused(e, aid)}
              title={`Open ${aid} — pin as a key suspect`}
            >
              {aid}
            </button>
          ))}
        </div>
      )}

      <FeedbackControls
        item={item}
        recorded={recorded}
        isCorrectionOpen={isCorrectionOpen}
        explanation={explanation}
        onExplanationChange={onExplanationChange}
        onOpenCorrection={onOpenCorrection}
        onCancelCorrection={onCancelCorrection}
        onSubmit={onSubmitFeedback}
      />
    </div>
  );
}
