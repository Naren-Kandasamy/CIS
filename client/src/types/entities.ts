// Domain model for entities surfaced by the retrieval pipeline (people, FIR
// case files, locations) and inspected in the EntityDrawer. Promoted verbatim
// out of hooks/useEntityDrawer.ts so pages/stores can share it without importing
// a hook.

export type EntityType = 'person' | 'fir' | 'location' | 'victim';

export interface LinkedNode {
  id: string;
  label: string;
  /** Neighbour node type; `resolveLinkedNodes` falls back to 'unknown'. */
  type: EntityType | string;
  edgeLabel?: string;
}

export interface SelectedEntity {
  type: EntityType;
  id: string;
  label: string;
  data?: Record<string, any>;
  evidenceItems?: any[];
  linkedNodes?: LinkedNode[];
}
