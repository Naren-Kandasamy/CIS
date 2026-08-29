import { useRef, useState } from 'react';
import type { CSSProperties, PointerEvent as ReactPointerEvent, ReactNode } from 'react';
import type { BoardCard } from '../../types/board';
import { Pushpin } from './Pushpin';

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
  children,
}: BoardCardFrameProps) {
  const [dragging, setDragging] = useState(false);
  const movedRef = useRef(false);

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
    </div>
  );
}
