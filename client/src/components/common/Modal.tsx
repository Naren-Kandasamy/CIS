import { useEffect, useRef, type ReactNode } from 'react';

// Small dialog primitive in the Case File idiom. Escape to close, click-outside
// to close, focus moves in on open and returns to the trigger on close. Replaces
// the browser prompt()/confirm() the old sidebar used.

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: ReactNode;
  /** Rendered in the footer, right-aligned. */
  actions?: ReactNode;
  labelledBy?: string;
}

export default function Modal({ open, onClose, title, description, children, actions }: ModalProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  // Keep the latest onClose without making it an effect dependency. Callers
  // pass a fresh inline arrow every render; if the effect below re-ran on that,
  // its cleanup fired `returnFocusRef.current.focus()` on every keystroke —
  // focus jumped out of the field after one character.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const t = window.setTimeout(() => {
      cardRef.current?.querySelector<HTMLElement>(
        'input,textarea,select,button,[tabindex]:not([tabindex="-1"])',
      )?.focus();
    }, 0);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onCloseRef.current();
    };
    document.addEventListener('keydown', onKey);
    return () => {
      window.clearTimeout(t);
      document.removeEventListener('keydown', onKey);
      returnFocusRef.current?.focus?.();
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal-card"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={cardRef}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <h2 className="modal-title stamp-font">{title}</h2>
        {description && <p className="modal-description">{description}</p>}
        {children}
        {actions && <div className="modal-actions">{actions}</div>}
      </div>
    </div>
  );
}
