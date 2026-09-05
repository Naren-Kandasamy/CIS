import type { PinnedItem } from '../../types/board';
import { firLabel } from '../../lib/utils';

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// Compact case-file card for a pinned FIR citation. The board header is a
// short pinnable tag (like the suspect ACC-STORY-xxx tags), not the full
// crime number — that's shown as a secondary line instead.
export function FirCard({ pin }: { pin: PinnedItem }) {
  const c = pin.content as Record<string, any>;
  const d = (c.data as Record<string, any>) ?? {};
  const rawFirId = String(c.fir_id ?? d.fir_id ?? '').trim();
  const crimeNo = c.crime_no ?? d.crime_no;
  const tag = rawFirId
    ? `FIR ${UUID_RE.test(rawFirId) ? rawFirId.slice(0, 8).toUpperCase() : rawFirId}`
    : firLabel(crimeNo, rawFirId, 'FIR');
  const crimeType = c.crime_type ?? d.crime_type;
  const district = d.district;
  const confidence = c.confidence ?? d.confidence;

  return (
    <div className="fir-card">
      <div className="fir-card-id">{tag}</div>
      {crimeNo && <div className="fir-card-row fir-card-crime-no">Crime No. {String(crimeNo)}</div>}
      {crimeType && <div className="fir-card-row">{String(crimeType)}</div>}
      {district && <div className="fir-card-row">{String(district)}</div>}
      {confidence && (
        <div className="fir-card-row" style={{ textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {String(confidence)} confidence
        </div>
      )}
    </div>
  );
}
