import React from 'react';
import { PIPELINE_STEPS } from '../../types/chat';

// Phase 3: the streaming pipeline stepper, extracted verbatim from
// SessionChatPage's message map (originally App.tsx:779-824). Renders nothing
// until the assistant message carries a `status`.

export function PipelineProgress({ status }: { status?: string }) {
  if (!status) return null;

  const currentStepIdx = PIPELINE_STEPS.findIndex((s) => s.key === status.toLowerCase());

  return (
    <div className="w-full max-w-lg mb-4 mt-2">
      <div className="flex items-center justify-between mb-2">
        <div className="status-pill inline-flex items-center gap-2 py-1 px-3">
          <div
            className="pulse w-1.5 h-1.5 rounded-full animate-ping"
            style={{ background: 'var(--accent-primary)' }}
          />
          <span className="uppercase font-medium text-[11px]">{status}...</span>
        </div>
      </div>
      <div className="flex items-center gap-1 w-full mt-3 px-1">
        {PIPELINE_STEPS.map((step, idx) => {
          const isCompleted = currentStepIdx > idx;
          const isActive = status.toLowerCase() === step.key;
          return (
            <React.Fragment key={step.key}>
              <div className="flex flex-col items-center flex-1 relative group">
                <div
                  className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-semibold transition-all duration-300 border"
                  style={
                    isCompleted
                      ? { background: 'var(--accent-primary)', borderColor: 'var(--accent-primary)', color: 'var(--bg-secondary)' }
                      : isActive
                        ? { background: 'var(--accent-glow)', borderColor: 'var(--accent-primary)', color: 'var(--accent-primary)' }
                        : { background: 'var(--bg-tertiary)', borderColor: 'var(--glass-border)', color: 'var(--text-tertiary)' }
                  }
                >
                  {isCompleted ? '✓' : idx + 1}
                </div>
                <span
                  className={`text-[8px] mt-1.5 hidden md:block whitespace-nowrap transition-colors ${isActive ? 'font-medium' : ''}`}
                  style={{ color: isActive ? 'var(--accent-primary)' : isCompleted ? 'var(--text-secondary)' : 'var(--text-tertiary)' }}
                >
                  {step.label}
                </span>
              </div>
              {idx < PIPELINE_STEPS.length - 1 && (
                <div
                  className="h-0.5 flex-1 mx-0.5 rounded transition-all duration-300"
                  style={{ background: isCompleted ? 'var(--accent-primary)' : 'var(--glass-border)' }}
                />
              )}
            </React.Fragment>
          );
        })}
      </div>
    </div>
  );
}
