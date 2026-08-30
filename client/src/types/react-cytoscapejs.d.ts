// Minimal ambient types for react-cytoscapejs, which ships no .d.ts of its
// own. Covers only the props NetworkGraph.tsx actually uses.
declare module 'react-cytoscapejs' {
  import type { Component } from 'react';
  import type {
    Core,
    ElementDefinition,
    LayoutOptions,
    Stylesheet,
  } from 'cytoscape';

  export interface CytoscapeComponentProps {
    elements: ElementDefinition[] | { data: Record<string, unknown> }[];
    id?: string;
    className?: string;
    style?: React.CSSProperties;
    layout?: LayoutOptions | { name: string; [key: string]: unknown };
    stylesheet?: Stylesheet[] | string;
    cy?: (cy: Core) => void;
    pan?: { x: number; y: number };
    zoom?: number;
    minZoom?: number;
    maxZoom?: number;
    boxSelectionEnabled?: boolean;
    autoungrabify?: boolean;
    wheelSensitivity?: number;
    [key: string]: unknown;
  }

  export default class CytoscapeComponent extends Component<CytoscapeComponentProps> {
    static normalizeElements(
      data:
        | { nodes: unknown[]; edges: unknown[] }
        | ElementDefinition[],
    ): ElementDefinition[];
  }
}
