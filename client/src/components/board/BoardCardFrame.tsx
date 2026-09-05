import { useRef, useState } from 'react';
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import { Pin, PinOff, Trash2 } from 'lucide-react';
import type { BoardCard } from '../../types/board';
import { Pushpin } from './Pushpin';

const MIN_W = 120;
const MIN_H = 90;

// Draggable pinned-paper wrapper. Positioning is in *board* coordinates; the
// parent surface applies the pan/zoom transform, so screen deltas are divided
// by `zoom` here. Pointer moves are tracked on `window` (no pointer capture) so
// interactive descendants marked [data-no-drag] keep their own click handling.

interface BoardCardFrameProps {
  card: BoardCard;
  zoom: number;
  linking: boolean;
  isLinkSource: boolean;
  onDragMove: (x: number, y: number) => void;
  onDragEnd: () => void;
  onSelect: () => void;
  /** Resize the card live (board-coordinate w/h); called continuously while dragging the handle. */
  onResize?: (w: number, h: number) => void;
  onResizeEnd?: () => void;
  /** Present only for kinds that support removal from the board (fir/suspect); omit to hide the button. */
  onDelete?: () => void;
  /** Toggle whether this card's suspect/citation is pinned in the case_board
   * log (independent of the card's presence on the board). Present only for
   * fir/suspect kinds. */
  onTogglePin?: () => void;
  pinned?: boolean;
  children: ReactNode;
}

export function BoardCardFrame({
  card,
  zoom,
  linking,
  isLinkSource,
  onDragMove,
  onDragEnd,
  onSelect,
  onResize,
  onResizeEnd,
  onDelete,
  onTogglePin,
  pinned,
  children,
}: BoardCardFrameProps) {
  const [dragging, setDragging] = useState(false);
  const [resizing, setResizing] = useState(false);
  const movedRef = useRef(false);

  const handleResizePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0 || !onResize) return;
    e.stopPropagation();
    const startX = e.clientX;
    const startY = e.clientY;
    const originW = card.w;
    const originH = card.h;
    setResizing(true);

    const move = (ev: PointerEvent) => {
      const dw = (ev.clientX - startX) / zoom;
      const dh = (ev.clientY - startY) / zoom;
      onResize(Math.max(MIN_W, originW + dw), Math.max(MIN_H, originH + dh));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      setResizing(false);
      onResizeEnd?.();
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const handlePointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('[data-no-drag]')) return;
    e.stopPropagation();

    const startX = e.clientX;
    const startY = e.clientY;
    const originX = card.x;
    const originY = card.y;
    movedRef.current = false;

    const move = (ev: PointerEvent) => {
      const dx = (ev.clientX - startX) / zoom;
      const dy = (ev.clientY - startY) / zoom;
      if (!movedRef.current && Math.abs(dx) + Math.abs(dy) > 3) {
        movedRef.current = true;
        setDragging(true);
      }
      if (movedRef.current) onDragMove(originX + dx, originY + dy);
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      setDragging(false);
      if (movedRef.current) onDragEnd();
      else onSelect();
    };

    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    // Only act when the frame itself has focus. Without this guard the space /
    // enter keydown from a child <textarea>/<input> (free-note text, hypothesis
    // resolve reason, …) bubbles up here and gets preventDefault()'d — you
    // couldn't type a space inside a card.
    if (e.target !== e.currentTarget) return;
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      onSelect();
    }
  };

  const style: CSSProperties = {
    left: card.x,
    top: card.y,
    width: card.w,
    minHeight: card.h,
    transform: `rotate(${card.rotation ?? 0}deg)`,
  };

  const cls = [
    'board-card',
    dragging ? 'is-dragging' : '',
    resizing ? 'is-resizing' : '',
    linking && isLinkSource ? 'link-source' : '',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={cls}
      style={style}
      onPointerDown={handlePointerDown}
      onKeyDown={handleKeyDown}
      role="button"
      tabIndex={0}
      aria-label={`${card.kind} card`}
    >
      <Pushpin color={card.color} />
      {children}
      {(onDelete || onTogglePin) && (
        <div className="board-card-actions" data-no-drag>
          {onTogglePin && (
            <button
              type="button"
              data-no-drag
              className={`board-mini-btn board-card-action ${pinned ? '' : 'is-unpinned'}`}
              title={pinned ? 'Unpin — remove from the workspace lists' : 'Pin — add to the workspace lists'}
              onClick={(e) => {
                e.stopPropagation();
                onTogglePin();
              }}
            >
              {pinned ? <Pin size={11} /> : <PinOff size={11} />}
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              data-no-drag
              className="board-mini-btn danger board-card-action"
              title={`Remove this ${card.kind} card from the board`}
              onClick={(e) => {
                e.stopPropagation();
                onDelete();
              }}
            >
              <Trash2 size={11} />
            </button>
          )}
        </div>
      )}
      {onResize && (
        <div
          data-no-drag
          className="board-card-resize-handle"
          onPointerDown={handleResizePointerDown}
          title="Drag to resize"
        />
      )}
    </div>
  );
}
