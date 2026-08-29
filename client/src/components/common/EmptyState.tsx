import type { ReactNode } from 'react';

// One empty-state treatment reused across the app: no cases, no sessions, no
// pinned evidence, empty board. Replaces the old alert('select a case first').

interface EmptyStateProps {
  icon?: ReactNode;
  title: string;
  message?: string;
  action?: ReactNode;
}

export default function EmptyState({ icon, title, message, action }: EmptyStateProps) {
  return (
    <div className="empty-state" role="status">
      {icon && <div className="empty-state-icon">{icon}</div>}
      <p className="empty-state-title stamp-font">{title}</p>
      {message && <p className="empty-state-message">{message}</p>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  );
}
