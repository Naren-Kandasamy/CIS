// Helpers for turning a synthesis answer into a starting point for a hypothesis.
// A synthesised answer is markdown with `### Field Urgent Summary`,
// `### Analytical Synthesis` and `### Evidence Summary` sections; the analytical
// paragraph is the officer's natural first draft of a working theory.

const FIR_CITATION_RE = /\s*\[FIR:[^\]]*\]/gi;

/**
 * Pull the "Analytical Synthesis" prose out of a synthesis answer. Returns null
 * when there's no such section (profile-mode answers, follow-ups, errors) so the
 * caller can decide not to offer the suggestion.
 */
export function extractAnalysis(markdown: string | undefined): string | null {
  if (!markdown) return null;
  const m = markdown.match(
    /#{1,4}\s*Analytical Synthesis\s*\n+([\s\S]*?)(?:\n#{1,4}\s|\n\**All outputs require|$)/i,
  );
  if (!m) return null;
  const text = m[1]
    .replace(FIR_CITATION_RE, '')
    .replace(/\s*,\s*(?=[.,)])/g, '')
    .replace(/\(\s*\)/g, '')
    .replace(/\s+/g, ' ')
    .trim();
  return text.length >= 20 ? text : null;
}

/** Unique FIR ids + accused ids referenced by a message's evidence items. */
export function collectLinkedEntities(
  evidence: { fir_id?: string; data?: Record<string, unknown> }[] | undefined,
): string[] {
  const out = new Set<string>();
  for (const e of evidence ?? []) {
    if (e.fir_id) out.add(e.fir_id);
    const acc = (e.data as Record<string, unknown> | undefined)?.accused_ids;
    if (Array.isArray(acc)) {
      for (const a of acc) if (a) out.add(String(a));
    }
  }
  return [...out];
}
