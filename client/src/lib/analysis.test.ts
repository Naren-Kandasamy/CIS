import { describe, expect, it } from 'vitest';
import { collectLinkedEntities, extractAnalysis, extractCitedFirIds } from './analysis';

const ANSWER = `### Field Urgent Summary
- Mysuru (2024-10-28): Robbery incident reported [FIR: e0217466-14ff-4f5c-a196-0c48781bc195].

### Analytical Synthesis
The retrieved evidence indicates a pattern of group-based robberies in Mysuru
spanning from 2020 to 2024. Evidence suggests a coordinated modus operandi
involving multiple vehicles and mobile communication, consistent across all cases
[FIR: dca8e229-d436-4e16-9b57-824328e8d9e9], [FIR: 7d299603-1152-4e7a-83d4-463627b1fe0e].

### Evidence Summary
- FIR: e0217466-14ff-4f5c-a196-0c48781bc195 (Mysuru, 2024-10-28): low confidence.

All outputs require officer verification before operational action.`;

describe('extractAnalysis', () => {
  it('pulls the Analytical Synthesis paragraph and strips [FIR: …] citations', () => {
    const out = extractAnalysis(ANSWER);
    expect(out).toBeTruthy();
    expect(out).toContain('pattern of group-based robberies in Mysuru');
    expect(out).not.toMatch(/\[FIR:/);
    expect(out).not.toContain('### Evidence Summary');
    expect(out).not.toContain('All outputs require');
    // no dangling ", ." left after citation removal
    expect(out).not.toMatch(/,\s*\./);
  });

  it('returns null when there is no Analytical Synthesis section', () => {
    expect(extractAnalysis('### Field Urgent Summary\n- one line only.')).toBeNull();
    expect(extractAnalysis('')).toBeNull();
    expect(extractAnalysis(undefined)).toBeNull();
  });

  it('handles a section that runs to end of string (no trailing headings)', () => {
    const out = extractAnalysis('### Analytical Synthesis\nA short but sufficient theory statement here.');
    expect(out).toBe('A short but sufficient theory statement here.');
  });
});

describe('collectLinkedEntities', () => {
  it('unions FIR ids and accused_ids, de-duplicated', () => {
    const ids = collectLinkedEntities([
      { fir_id: 'fir-1', data: { accused_ids: ['ACC-1', 'ACC-2'] } },
      { fir_id: 'fir-2', data: { accused_ids: ['ACC-2', 'ACC-3'] } },
      { fir_id: 'fir-1', data: {} },
    ]);
    expect(new Set(ids)).toEqual(new Set(['fir-1', 'fir-2', 'ACC-1', 'ACC-2', 'ACC-3']));
  });

  it('is safe on missing / empty evidence', () => {
    expect(collectLinkedEntities(undefined)).toEqual([]);
    expect(collectLinkedEntities([{ fir_id: '' }, { data: {} } as any])).toEqual([]);
  });
});

describe('extractCitedFirIds', () => {
  it('pulls unique FIR ids out of [FIR: …] citations', () => {
    const ids = extractCitedFirIds(ANSWER);
    expect(new Set(ids)).toEqual(
      new Set([
        'e0217466-14ff-4f5c-a196-0c48781bc195',
        'dca8e229-d436-4e16-9b57-824328e8d9e9',
        '7d299603-1152-4e7a-83d4-463627b1fe0e',
      ]),
    );
  });

  it('returns [] when there are no citations / no input', () => {
    expect(extractCitedFirIds('no citations here')).toEqual([]);
    expect(extractCitedFirIds(undefined)).toEqual([]);
  });
});
