import React, { useRef, useEffect } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import type { SelectedEntity } from '../../hooks/useEntityDrawer';
import { resolveLinkedNodes, matchEvidenceByFirId } from '../../hooks/useEntityDrawer';

interface NetworkGraphProps {
  elements?: any[];
  onNodeClick?: (entity: SelectedEntity) => void;
  /** Full evidence array so the drawer can show narrative detail */
  evidence?: any[];
}

const DEFAULT_ELEMENTS = [
  // Nodes
  { data: { id: 'fir1', label: 'FIR 12/2024', type: 'fir' }, classes: 'fir' },
  { data: { id: 'fir2', label: 'FIR 45/2023', type: 'fir' }, classes: 'fir' },
  { data: { id: 'p1', label: 'Ramesh Gowda', type: 'person' }, classes: 'person' },
  { data: { id: 'p2', label: 'Siddesh K.', type: 'person' }, classes: 'person' },
  { data: { id: 'p3', label: 'Anand Swamy', type: 'person' }, classes: 'person' },
  { data: { id: 'loc1', label: 'Belagavi', type: 'location' } },
  { data: { id: 'loc2', label: 'Bengaluru City', type: 'location' } },

  // Edges
  { data: { source: 'p1', target: 'fir1', label: 'Accused' } },
  { data: { source: 'p2', target: 'fir1', label: 'Conspirator' } },
  { data: { source: 'p3', target: 'fir2', label: 'Abettor' } },
  { data: { source: 'fir1', target: 'loc1', label: 'Occurred At' } },
  { data: { source: 'fir2', target: 'loc2', label: 'Occurred At' } },
  { data: { source: 'p1', target: 'p2', label: 'Associate' } }
];

export default function NetworkGraph({ elements, onNodeClick, evidence }: NetworkGraphProps) {
  const graphElements = elements && elements.length > 0 ? elements : DEFAULT_ELEMENTS;
  const cyRef = useRef<any>(null);

  // Attach tap listener whenever elements or callback changes
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || !onNodeClick) return;

    const handleTap = (evt: any) => {
      const node = evt.target;
      const data = node.data();
      const nodeId: string = data.id;
      const rawType: string = data.type ?? 'fir';
      const type = (['person', 'fir', 'location'].includes(rawType) ? rawType : 'fir') as SelectedEntity['type'];

      const linkedNodes = resolveLinkedNodes(nodeId, graphElements);

      // Match evidence items for this node
      let evidenceItems: any[] = [];
      if (type === 'fir' && evidence) {
        evidenceItems = matchEvidenceByFirId(nodeId, evidence);
      } else if (type === 'person' && evidence) {
        // For a person, collect evidence for all linked FIR nodes
        for (const ln of linkedNodes.filter(n => n.type === 'fir')) {
          evidenceItems.push(...matchEvidenceByFirId(ln.id, evidence));
        }
      }

      onNodeClick({ type, id: nodeId, label: data.label ?? nodeId, data, evidenceItems, linkedNodes });
    };

    cy.on('tap', 'node', handleTap);
    return () => {
      cy.removeListener('tap', 'node', handleTap);
    };
  }, [graphElements, onNodeClick, evidence]);

  return (
    <div style={{ height: '360px', width: '100%', boxSizing: 'border-box' }}>
      <div style={{ height: '100%', width: '100%', border: '1px solid var(--glass-border)', borderRadius: '2px', overflow: 'hidden', background: 'var(--bg-primary)' }}>
        <CytoscapeComponent
          elements={graphElements}
          layout={{ name: 'cose' }}
          style={{ width: '100%', height: '100%' }}
          cy={(cy) => { cyRef.current = cy; }}
          stylesheet={[
            {
              selector: 'node',
              style: {
                'background-color': '#4a5a7a',
                'label': 'data(label)',
                'color': '#241d14',
                'text-outline-color': '#e9e1cd',
                'text-outline-width': 2,
                'font-size': '12px',
                'font-family': 'IBM Plex Mono, monospace',
                'cursor': 'pointer',
                'transition-property': 'background-color, border-width, border-color',
                'transition-duration': '0.15s',
              } as any
            },
            {
              selector: 'node:hover',
              style: {
                'border-width': 3,
                'border-color': '#a9791f',
              } as any
            },
            {
              selector: 'node:selected',
              style: {
                'border-width': 3,
                'border-color': '#8a2a24',
                'background-color': '#b03b35',
              } as any
            },
            {
              selector: 'node.person',
              style: {
                'background-color': '#8a2a24',
                'shape': 'ellipse'
              }
            },
            {
              selector: 'node.fir',
              style: {
                'background-color': '#2f4a3c',
                'shape': 'rectangle'
              }
            },
            {
              selector: 'edge',
              style: {
                'width': 1.5,
                'line-color': '#8a7d67',
                'target-arrow-color': '#8a7d67',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'label': 'data(label)',
                'color': '#5c5140',
                'font-size': '10px',
                'font-family': 'IBM Plex Mono, monospace',
                'text-background-opacity': 1,
                'text-background-color': '#e9e1cd',
                'text-background-padding': '2px'
              }
            }
          ]}
        />
      </div>
    </div>
  );
}
