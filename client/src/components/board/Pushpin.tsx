import type { CSSProperties } from 'react';

// A single pushpin head. `color` is a token name or hex from BoardCard.color;
// it is passed straight through as the CSS custom prop the stylesheet reads.
export function Pushpin({ color }: { color: string }) {
  return <span className="board-pin" style={{ '--pin-color': color } as CSSProperties} aria-hidden />;
}
