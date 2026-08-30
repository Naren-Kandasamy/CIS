import { FileText } from 'lucide-react';
import type { PinnedItem } from '../../types/board';
import { useEntityStore } from '../../stores/entityStore';

// Phase 4: persistent citations for a case — every FIR pinned to the board from
// any chat session. Replaces the old recent-conversations mock table, which was
// fed by the last query's in-memory `visualization`.

export function CitationsTable({ citations }: { citations: PinnedItem[] }) {
  const openEntity = useEntityStore((s) => s.open);

  const openRow = (pin: PinnedItem) => {
    const c = pin.content as Record<string, any>;
    const firId = c.fir_id ?? c.data?.crime_no ?? 'case';
    openEntity({
      type: 'fir',
      id: firId,
      label: c.data?.crime_no ?? c.fir_id ?? 'Case File',
      data: c.data ?? c,
      evidenceItems: [c],
    });
  };

  return (
    <div className="dossier-panel dossier-paperclip" style={{ padding: '20px' }}>
      <h3 className="dossier-panel-title text-base mb-1">Pinned Citations</h3>
      <p className="dossier-panel-subtitle text-xs mb-4">
        {citations.length} FIR{citations.length === 1 ? '' : 's'} pinned to this case board.
      </p>

      {citations.length === 0 ? (
        <div className="flex items-center gap-2 text-xs" style={{ color: 'var(--text-tertiary)' }}>
          <FileText size={14} /> Pin evidence from a chat session to build the case record.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm" style={{ borderCollapse: 'collapse' }}>
            <thead>
              <tr className="dossier-table-head text-left text-xs uppercase tracking-wider">
                <th className="py-2 pr-3">FIR / Crime No.</th>
                <th className="py-2 pr-3">Type</th>
                <th className="py-2 pr-3">District</th>
                <th className="py-2 pr-3">Confidence</th>
              </tr>
            </thead>
            <tbody>
              {citations.map((pin, idx) => {
                const c = pin.content as Record<string, any>;
                return (
                  <tr
                    key={idx}
                    className="dossier-row entity-clickable"
                    style={{ borderTop: '1px dashed var(--paper-line)', cursor: 'pointer' }}
                    onClick={() => openRow(pin)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') openRow(pin);
                    }}
                  >
                    <td className="py-2 pr-3 dossier-id font-mono">
                      {c.data?.crime_no ?? c.fir_id ?? '—'}
                    </td>
                    <td className="py-2 pr-3">{c.data?.crime_type ?? c.crime_type ?? '—'}</td>
                    <td className="py-2 pr-3">{c.data?.district ?? '—'}</td>
                    <td className="py-2 pr-3 dossier-mono text-xs uppercase">
                      {c.confidence ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
