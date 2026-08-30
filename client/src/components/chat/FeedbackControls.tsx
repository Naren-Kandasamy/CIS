import type { Message } from '../../types/chat';
import type { FeedbackVerdict } from '../../stores/chatStore';

// Phase 3: the per-citation feedback block, extracted verbatim from
// SessionChatPage's evidence card (originally App.tsx feedback controls). The
// "one correction box open at a time" state stays lifted in MessageList.

type EvidenceItem = NonNullable<Message['evidence']>[number];

interface FeedbackControlsProps {
  item: EvidenceItem;
  recorded?: { verdict: FeedbackVerdict };
  isCorrectionOpen: boolean;
  explanation: string;
  onExplanationChange: (value: string) => void;
  onOpenCorrection: () => void;
  onCancelCorrection: () => void;
  onSubmit: (item: EvidenceItem, verdict: 'confirmed' | 'corrected', explanation?: string) => void;
}

export function FeedbackControls({
  item,
  recorded,
  isCorrectionOpen,
  explanation,
  onExplanationChange,
  onOpenCorrection,
  onCancelCorrection,
  onSubmit,
}: FeedbackControlsProps) {
  return (
    <div
      className="feedback-controls mt-2 pt-2 border-t"
      style={{ borderColor: 'var(--glass-border)' }}
      onClick={(e) => e.stopPropagation()}
    >
      {recorded ? (
        <div className="text-[10px] text-emerald-700 font-medium flex items-center gap-1">
          <span>✓</span> Feedback recorded ({recorded.verdict})
        </div>
      ) : (
        <div className="flex flex-col gap-2">
          {isCorrectionOpen ? (
            <div className="flex flex-col gap-2 mt-1">
              <textarea
                className="w-full text-xs p-1.5 rounded"
                style={{ background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--glass-border)', outline: 'none' }}
                placeholder="Explain the correction (required)..."
                value={explanation}
                onChange={(e) => onExplanationChange(e.target.value)}
                rows={2}
                required
              />
              <div className="flex gap-2 justify-end">
                <button
                  type="button"
                  onClick={onCancelCorrection}
                  className="px-2 py-1 text-[10px] rounded border"
                  style={{ background: 'var(--bg-tertiary)', color: 'var(--text-secondary)', borderColor: 'var(--glass-border)', cursor: 'pointer' }}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={!explanation.trim()}
                  onClick={() => onSubmit(item, 'corrected', explanation)}
                  className="px-2 py-1 text-[10px] rounded text-white"
                  style={{ background: explanation.trim() ? 'var(--accent-primary)' : 'var(--text-tertiary)', cursor: explanation.trim() ? 'pointer' : 'not-allowed' }}
                >
                  Submit
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-center gap-2">
              <span className="text-[10px]" style={{ color: 'var(--text-tertiary)' }}>
                Was this connection useful?
              </span>
              <button
                type="button"
                className="px-2 py-0.5 text-[10px] rounded border"
                style={{ borderColor: 'rgba(47, 74, 60, 0.5)', color: 'var(--accent-secondary)', cursor: 'pointer', background: 'transparent' }}
                onClick={() => onSubmit(item, 'confirmed')}
              >
                ✓ Confirm
              </button>
              <button
                type="button"
                className="px-2 py-0.5 text-[10px] rounded border"
                style={{ borderColor: 'rgba(138, 42, 36, 0.5)', color: 'var(--accent-primary)', cursor: 'pointer', background: 'transparent' }}
                onClick={onOpenCorrection}
              >
                ✗ Correct
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
