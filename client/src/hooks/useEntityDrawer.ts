import { useState, useCallback } from 'react';

// Types live in ../types/entities.ts now; re-exported here so existing importers
// (components/dashboard/*, App.tsx) keep working unchanged.
export type { EntityType, SelectedEntity, LinkedNode } from '../types/entities';
import type { SelectedEntity, LinkedNode } from '../types/entities';

export function useEntityDrawer() {
  const [selectedEntity, setSelectedEntity] = useState<SelectedEntity | null>(null);

  const openEntity = useCallback((entity: SelectedEntity) => {
    setSelectedEntity(entity);
  }, []);

  const closeDrawer = useCallback(() => {
    setSelectedEntity(null);
  }, []);

  return { selectedEntity, openEntity, closeDrawer };
}

// ─── helpers ──────────────────────────────────────────────────────────────────

/**
 * Given a node id and the full flat cytoscape elements array, resolve all
 * directly connected nodes (one hop) with their edge relationship label.
 */
export function resolveLinkedNodes(
  nodeId: string,
  elements: any[]
): LinkedNode[] {
  const edges = elements.filter(
    (el) =>
      el.data?.source !== undefined && // is an edge
      (el.data.source === nodeId || el.data.target === nodeId)
  );

  const linked: LinkedNode[] = [];
  const seen = new Set<string>();

  for (const edge of edges) {
    const isSource = edge.data.source === nodeId;
    const neighborId = isSource ? edge.data.target : edge.data.source;
    if (seen.has(neighborId)) continue;
    seen.add(neighborId);

    const neighborEl = elements.find(
      (el) => el.data?.id === neighborId && el.data?.source === undefined
    );
    if (!neighborEl) continue;

    linked.push({
      id: neighborId,
      label: neighborEl.data.label ?? neighborId,
      type: neighborEl.data.type ?? 'unknown',
      edgeLabel: edge.data.label ?? '',
    });
  }

  return linked;
}

/**
 * Match evidence[] items to a given FIR id (loose match — the evidence fir_id
 * may be stored as "FIR-123", "FIR 123/2024", or just the raw id).
 */
export function matchEvidenceByFirId(firId: string, evidence: any[]): any[] {
  if (!firId || !evidence?.length) return [];
  const normalized = firId.replace(/[-_\s]/g, '').toLowerCase();
  return evidence.filter((item) => {
    const candidate = (item.fir_id ?? '').replace(/[-_\s]/g, '').toLowerCase();
    return candidate === normalized || candidate.includes(normalized) || normalized.includes(candidate);
  });
}
