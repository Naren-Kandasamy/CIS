import type { Message } from '../../types/chat';
import type { FeedbackVerdict } from '../../stores/chatStore';
import { FeedbackControls } from './FeedbackControls';

// Phase 3: a single retrieved-evidence citation card, extracted verbatim from
// SessionChatPage's evidence grid (originally App.tsx:842-969).

type EvidenceItem = NonNullable<Message['evidence']>[number];

interface EvidenceCardProps {
  item: EvidenceItem;
  idx: number;
  openEntity: (entity: {
    type: 'fir';
    id: string;
    label: string;
    data: Record<string, unknown>;
    evidenceItems: EvidenceItem[];
  }) => void;
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
  const confidenceTier = String(item.confidence ?? '').toLowerCase();
  const confidenceColor =
    confidenceTier === 'high'
      ? 'text-emerald-800 bg-emerald-100 border-emerald-300'
      : confidenceTier === 'medium'
        ? 'text-amber-800 bg-amber-100 border-amber-300'
        : 'text-rose-800 bg-rose-100 border-rose-300';
  const openThis = () =>
    openEntity({
      type: 'fir',
      id: item.fir_id ?? `evidence-${idx}`,
      label: item.fir_id ?? 'Case File',
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
      aria-label={`View details for ${item.data?.crime_no || item.fir_id || 'case'}`}
    >
      <div
        className="flex items-center justify-between pb-2"
        style={{ borderBottom: '1px dashed var(--paper-line)' }}
      >
        <div className="font-mono font-medium text-sm truncate" style={{ color: 'var(--text-primary)' }}>
          {item.data?.crime_no || item.fir_id || 'No Case ID'}
        </div>
        {item.confidence && (
          <span
            className={`text-[10px] px-1.5 py-0.5 rounded-sm border uppercase tracking-wider font-semibold whitespace-nowrap ${confidenceColor}`}
          >
            {item.confidence}
          </span>
        )}
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
          className="text-[9px] mt-1"
          style={{ color: 'var(--text-tertiary)', fontFamily: 'IBM Plex Mono, monospace' }}
        >
          Click to expand →
        </div>
      </div>

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
