import { Maximize2, Minus, Plus, RotateCcw, Spline, StickyNote } from 'lucide-react';

interface Props {
  zoom: number;
  linking: boolean;
  onAddNote: () => void;
  onToggleLink: () => void;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onFit: () => void;
  onReset: () => void;
}

export function BoardToolbar({
  zoom,
  linking,
  onAddNote,
  onToggleLink,
  onZoomIn,
  onZoomOut,
  onFit,
  onReset,
}: Props) {
  return (
    <div className="board-toolbar" data-no-drag>
      <button type="button" onClick={onAddNote} title="Add a blank note">
        <StickyNote size={13} /> Note
      </button>
      <button
        type="button"
        className={linking ? 'is-active' : ''}
        onClick={onToggleLink}
        title="Cord two cards together"
      >
        <Spline size={13} /> Link
      </button>
      <span className="board-toolbar-sep" />
      <button type="button" onClick={onZoomOut} title="Zoom out" disabled={zoom <= 0.4}>
        <Minus size={13} />
      </button>
      <span className="board-zoom-label">{Math.round(zoom * 100)}%</span>
      <button type="button" onClick={onZoomIn} title="Zoom in" disabled={zoom >= 2}>
        <Plus size={13} />
      </button>
      <span className="board-toolbar-sep" />
      <button type="button" onClick={onFit} title="Fit all cards">
        <Maximize2 size={13} />
      </button>
      <button type="button" onClick={onReset} title="Reset view">
        <RotateCcw size={13} />
      </button>
    </div>
  );
}
