import { useEffect, useRef, useState } from 'react';
import { ImagePlus, Trash2 } from 'lucide-react';
import type { BoardCard } from '../../types/board';

// A photo tile the officer fills themselves — evidence, an accused, a victim,
// a location shot. Pinned and dragged exactly like every other card; once it
// has a refId-less identity of its own it can be corded via the Link tool same
// as a hypothesis or suspect card.

interface Props {
  card: BoardCard;
  onChangeLabel: (label: string) => void;
  onPickFile: (file: File) => void;
  onRemove: () => void;
}

export function PhotoCard({ card, onChangeLabel, onPickFile, onRemove }: Props) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(card.label ?? '');
  const inputRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    if (!editing) setDraft(card.label ?? '');
  }, [card.label, editing]);

  const commit = () => {
    setEditing(false);
    if (draft !== (card.label ?? '')) onChangeLabel(draft);
  };

  return (
    <div className="photo-card">
      <div
        className="photo-frame"
        onDoubleClick={() => fileRef.current?.click()}
        title={card.photoUrl ? 'Double-click to replace' : 'Double-click to add a photo'}
      >
        {card.photoUrl ? (
          <img src={card.photoUrl} alt={card.label || 'Pinned photo'} draggable={false} />
        ) : (
          <button
            type="button"
            data-no-drag
            className="photo-upload-placeholder"
            onClick={() => fileRef.current?.click()}
          >
            <ImagePlus size={20} />
            <span>Add photo</span>
          </button>
        )}
        <input
          ref={fileRef}
          data-no-drag
          type="file"
          accept="image/*"
          hidden
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) onPickFile(f);
            e.target.value = '';
          }}
        />
      </div>
      <div className="photo-caption" onDoubleClick={() => setEditing(true)}>
        {editing ? (
          <input
            ref={inputRef}
            data-no-drag
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === 'Enter') commit();
              if (e.key === 'Escape') {
                setDraft(card.label ?? '');
                setEditing(false);
              }
            }}
            placeholder="Who / what is this…"
          />
        ) : (
          <span className={card.label?.trim() ? '' : 'is-placeholder'}>
            {card.label?.trim() || 'Double-click to caption…'}
          </span>
        )}
      </div>
      <button
        type="button"
        data-no-drag
        className="board-mini-btn danger photo-remove"
        title="Remove photo"
        onClick={onRemove}
      >
        <Trash2 size={11} />
      </button>
    </div>
  );
}
