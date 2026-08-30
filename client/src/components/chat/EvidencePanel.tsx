import { Database } from 'lucide-react';
import type { Message } from '../../types/chat';
import type { SelectedEntity } from '../../types/entities';
import type { FeedbackVerdict } from '../../stores/chatStore';
import { EvidenceCard } from './EvidenceCard';

// Phase 3: the collapsible "Retrieved Evidence" panel, extracted verbatim from
// SessionChatPage's message map (originally App.tsx evidence card).

type EvidenceItem = NonNullable<Message['evidence']>[number];

export interface EvidenceFeedback {
  status: Record<string, { verdict: FeedbackVerdict }>;
  activeCorrectionId: string | null;
  explanation: string;
  onExplanationChange: (value: string) => void;
  onOpenCorrection: (key: string) => void;
  onCancelCorrection: () => void;
  onSubmit: (item: EvidenceItem, verdict: 'confirmed' | 'corrected', explanation?: string) => void;
}

interface EvidencePanelProps {
  evidence: EvidenceItem[];
  openEntity: (entity: SelectedEntity) => void;
  feedback: EvidenceFeedback;
}

export function EvidencePanel({ evidence, openEntity, feedback }: EvidencePanelProps) {
  return (
    <div className="evidence-card">
      <details className="evidence-details group" style={{ width: '100%' }}>
        <summary
          className="evidence-summary cursor-pointer select-none list-none flex items-center justify-between"
          style={{ borderBottom: 'none' }}
        >
          <div className="evidence-header flex items-center gap-2 text-sm">
            <Database size={14} style={{ color: 'var(--accent-secondary)' }} />
            <span>Retrieved Evidence ({evidence.length} Citations)</span>
          </div>
          <span
            className="text-xs group-open:rotate-180 transition-transform duration-200"
            style={{ color: 'var(--text-tertiary)' }}
          >
            ▼
          </span>
        </summary>
        <div className="evidence-content grid grid-cols-1 md:grid-cols-2 gap-3 mt-3">
          {evidence.map((item, idx) => {
            const key = item.edge_id || item.fir_id;
            return (
              <EvidenceCard
                key={idx}
                item={item}
                idx={idx}
                openEntity={openEntity}
                recorded={feedback.status[key]}
                isCorrectionOpen={feedback.activeCorrectionId === key}
                explanation={feedback.explanation}
                onExplanationChange={feedback.onExplanationChange}
                onOpenCorrection={() => feedback.onOpenCorrection(key)}
                onCancelCorrection={feedback.onCancelCorrection}
                onSubmitFeedback={feedback.onSubmit}
              />
            );
          })}
        </div>
      </details>
    </div>
  );
}
