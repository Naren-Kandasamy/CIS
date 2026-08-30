import type { PinnedItem } from '../../types/board';

// Compact case-file card for a pinned FIR citation.
export function FirCard({ pin }: { pin: PinnedItem }) {
  const c = pin.content as Record<string, any>;
  const d = (c.data as Record<string, any>) ?? {};
  const firId = String(c.fir_id ?? d.crime_no ?? 'FIR');
  const crimeType = c.crime_type ?? d.crime_type;
  const district = d.district;
  const confidence = c.confidence ?? d.confidence;

  return (
    <div className="fir-card">
      <div className="fir-card-id">{firId}</div>
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
