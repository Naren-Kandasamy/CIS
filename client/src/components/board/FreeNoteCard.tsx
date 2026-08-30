import { useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import type { BoardCard } from '../../types/board';

// A blank sticky the officer types on. Double-click (or the Edit affordance)
// swaps in a textarea; blur commits. `refId` may be set when the note stands in
// for a linked entity that has no other card yet.

interface Props {
  card: BoardCard;
  onChangeText: (text: string) => void;
  onRemove: () => void;
}

export function FreeNoteCard({ card, onChangeText, onRemove }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(card.text ?? '');
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) ref.current?.focus();
  }, [editing]);

  useEffect(() => {
    if (!editing) setDraft(card.text ?? '');
  }, [card.text, editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== (card.text ?? '')) onChangeText(draft);
  };

  return (
    <div className="free-note" onDoubleClick={() => setEditing(true)}>
      {editing ? (
        <textarea
          ref={ref}
          data-no-drag
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={(e) => {
            if (e.key === 'Escape') {
              setDraft(card.text ?? '');
              setEditing(false);
            }
          }}
        />
      ) : (
        <>
          {card.text?.trim() ? card.text : <span style={{ opacity: 0.5 }}>Double-click to write…</span>}
          <button
            type="button"
            data-no-drag
            className="board-mini-btn"
            style={{ position: 'absolute', top: 4, right: 4, padding: '2px 4px' }}
            title="Remove note"
            onClick={onRemove}
          >
            <Trash2 size={11} />
          </button>
        </>
      )}
    </div>
  );
}
