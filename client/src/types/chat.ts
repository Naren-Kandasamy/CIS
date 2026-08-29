// Chat + pipeline-result model. Replaces the `any`-typed local interfaces in
// App.tsx. `data` on an evidence item is the retrieval executor's FIR metadata
// blob (crime_type / district / Date / weapon / narrative / ...), left loose on
// purpose — the executor's key set drifts and every reader already guards it.

export type MessageRole = 'user' | 'assistant';

export interface Message {
  id: string;
  role: MessageRole;
  content: string;
  evidence?: EvidenceItem[];
  visualization?: Visualization;
  /** Human-readable pipeline stage while streaming, e.g. "retrieving evidence". */
  status?: string;
  isStreaming?: boolean;
}

export interface EvidenceItem {
  source?: string;
  fir_id: string;
  confidence?: string | number;
  relevance_score?: number;
  excluded?: boolean;
  exclusion_reason?: string;
  exclusion_type?: string;
  data?: Record<string, any>;
  edge_type?: string;
  edge_id?: string | null;
  crime_type?: string | null;
  flags?: unknown;
  convergent?: boolean;
  evidence_path?: unknown;
  similarity_reason?: string;
}

export interface CytoscapeElement {
  data: {
    id: string;
    label?: string;
    type?: EntityNodeType;
    details?: Record<string, any>;
    source?: string;
    target?: string;
  };
  classes?: string;
}

export type EntityNodeType = 'person' | 'fir' | 'location';

export interface Visualization {
  cytoscape?: { elements: CytoscapeElement[] };
  recharts?: {
    donut?: { name: string; value: number }[];
    trend?: { name: string; value: number }[];
  };
  leaflet?: { markers: { position: [number, number]; popup: string }[] };
}

/** Ordered pipeline stages the progress stepper renders. */
export const PIPELINE_STEPS = [
  { key: 'understanding query', label: 'NER & Intent' },
  { key: 'resolving entities', label: 'Entity Match' },
  { key: 'planning execution', label: 'DAG Planner' },
  { key: 'retrieving evidence', label: 'Retrieval' },
  { key: 'confidence scoring', label: 'Confidence' },
  { key: 'building visualization', label: 'Visualizer' },
  { key: 'synthesizing response', label: 'Synthesis' },
] as const;

export type QueryLanguage = 'en' | 'hi' | 'kn';
