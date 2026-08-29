import type { PinnedItem } from '../../types/board';

// Photo tile for a pinned suspect. No real mugshots in the data, so the frame
// shows initials in a sepia plate — the pushpin comes from BoardCardFrame.
export function SuspectTile({ pin }: { pin: PinnedItem }) {
  const c = pin.content as Record<string, any>;
  const name = String(c.label ?? c.name ?? c.id ?? 'Unknown');
  const initials = name
    .split(/\s+/)
    .map((w) => w[0])
    .filter(Boolean)
    .slice(0, 2)
    .join('')
    .toUpperCase();

  return (
    <div className="suspect-tile">
      <div className="suspect-photo">{initials || '?'}</div>
      <div className="suspect-name">{name}</div>
    </div>
  );
}
