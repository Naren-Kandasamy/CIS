import type { PinnedItem } from '../../types/board';
import { useEntityStore } from '../../stores/entityStore';

// Phase 4: persistent key-suspect quicklist — entities pinned with
// content_type 'suspect'. Falls back to a prompt when nothing is pinned yet
// (the old DashboardPanel showed hardcoded demo names here).

export function KeySuspectsList({ suspects }: { suspects: PinnedItem[] }) {
  const openEntity = useEntityStore((s) => s.open);

  return (
    <div
      className="dossier-panel dossier-paperclip flex flex-col gap-4"
      style={{ padding: '20px' }}
    >
      <div>
        <h3 className="dossier-panel-title text-base mb-1">Key Suspects</h3>
        <p className="dossier-panel-subtitle text-xs mb-4">Persons pinned to this case.</p>

        {suspects.length === 0 ? (
          <p className="text-xs" style={{ color: 'var(--text-tertiary)' }}>
            No suspects pinned yet.
          </p>
        ) : (
          <div className="space-y-3">
            {suspects.map((pin, idx) => {
              const c = pin.content as Record<string, any>;
              const label = c.label ?? c.name ?? c.id ?? 'Unknown';
              const initials = String(label)
                .split(' ')
                .map((n: string) => n[0])
                .join('')
                .slice(0, 2);
              return (
                <button
                  key={idx}
                  type="button"
                  className="flex items-center gap-3 py-1 pb-2 w-full text-left entity-clickable"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    borderBottom: '1px dashed var(--paper-line)',
                    cursor: 'pointer',
                  }}
                  onClick={() =>
                    openEntity({
                      type: 'person',
                      id: c.id ?? label,
                      label,
                      data: c.data ?? c,
                      linkedNodes: [],
                      evidenceItems: [],
                    })
                  }
                >
                  <div className="dossier-avatar w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0">
                    {initials}
                  </div>
                  <div>
                    <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                      {label}
                    </div>
                    <div className="dossier-mono text-xs">{c.role ?? 'Linked person'}</div>
                  </div>
                </button>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
