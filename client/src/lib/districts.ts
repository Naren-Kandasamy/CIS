// Approx. district-HQ centroids for the Karnataka districts present in the
// synthetic corpus. Used to place pinned FIRs on the case map — FIR records
// carry a `district` string but no lat/long of their own.

export const DISTRICT_CENTROIDS: Record<string, [number, number]> = {
  bengaluru: [12.9716, 77.5946],
  belagavi: [15.8497, 74.4977],
  mysuru: [12.2958, 76.6394],
  hubballi: [15.3647, 75.124],
  mangaluru: [12.9141, 74.856],
  kalaburagi: [17.3297, 76.8343],
};

/** Normalise a free-text district name to a DISTRICT_CENTROIDS key, or null. */
export function districtKey(name: unknown): string | null {
  const raw = String(name ?? '')
    .toLowerCase()
    .replace(/\b(city|district|rural|urban|dharwad|taluk|division)\b/g, '')
    .replace(/[^a-z]/g, '')
    .trim();
  if (!raw) return null;
  if (raw in DISTRICT_CENTROIDS) return raw;
  // common transliteration variants
  const alias: Record<string, string> = {
    bangalore: 'bengaluru',
    bengaluru: 'bengaluru',
    hubli: 'hubballi',
    hubballihubli: 'hubballi',
    mangalore: 'mangaluru',
    mysore: 'mysuru',
    belgaum: 'belagavi',
    gulbarga: 'kalaburagi',
  };
  if (raw in alias) return alias[raw];
  const hit = Object.keys(DISTRICT_CENTROIDS).find((k) => raw.includes(k) || k.includes(raw));
  return hit ?? null;
}

export function districtCentroid(name: unknown): [number, number] | null {
  const k = districtKey(name);
  return k ? DISTRICT_CENTROIDS[k] : null;
}
