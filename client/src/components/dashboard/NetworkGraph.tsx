import React, { useRef, useEffect, useState } from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
import type { SelectedEntity } from '../../hooks/useEntityDrawer';
import { resolveLinkedNodes, matchEvidenceByFirId } from '../../hooks/useEntityDrawer';

const encodeSvg = (svgString: string) => `data:image/svg+xml;base64,${btoa(svgString)}`;

const svgPerson = encodeSvg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff"><path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/></svg>`);
const svgFir = encodeSvg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>`);
const svgLocation = encodeSvg(`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#ffffff"><path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z"/></svg>`);

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
  const isFirstLayout = useRef<boolean>(true);

  const [nodeSize, setNodeSize] = useState<number>(42);
  const [edgeLength, setEdgeLength] = useState<number>(140);

  // Reset first-layout flag if underlying dataset structure changes entirely
  useEffect(() => {
    isFirstLayout.current = true;
  }, [elements]);

  // Balanced force layout execution loop
  useEffect(() => {
    const cy = cyRef.current;
    if (!cy || graphElements.length === 0) return;

    const layout = cy.layout({
      name: 'cose',
      animate: !isFirstLayout.current, // Smooth transitions when dragging sliders
      animationDuration: 300,
      fit: true,
      padding: 60,
      randomize: isFirstLayout.current, // Only scatter on initial mount
      nodeRepulsion: () => edgeLength * 9000, // Balanced multi-edge repulsion scaling
      idealEdgeLength: () => edgeLength,
      gravity: 0.15, // Extremely low gravity stops tightly linked clusters from collapsing
      edgeElasticity: () => 45,
      nodeOverlap: 60,
      refresh: 20,
      numIter: 1200
    });

    layout.run();
    isFirstLayout.current = false;
  }, [graphElements, edgeLength]);

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

  const handleNodeSizeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setNodeSize(parseInt(e.target.value, 10));
  };

  const handleEdgeLengthChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setEdgeLength(parseInt(e.target.value, 10));
  };

  const nodeSizePx = `${nodeSize}px`;
  const nodeSizeHoverPx = `${nodeSize + 2}px`;
  const nodeSizeSelectedPx = `${nodeSize + 6}px`;

  return (
    <div style={{ height: '440px', width: '100%', boxSizing: 'border-box', position: 'relative' }}>
      <div style={{ position: 'absolute', top: 12, right: 12, zIndex: 10, background: 'var(--bg-secondary)', padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--glass-border)', display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '11px', color: 'var(--text-secondary)', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <label style={{ width: '75px', fontWeight: 500 }}>Node Size</label>
          <input type="range" min="30" max="80" step="2" value={nodeSize} onChange={handleNodeSizeChange} style={{ width: '90px', cursor: 'pointer' }} />
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <label style={{ width: '75px', fontWeight: 500 }}>Edge Length</label>
          <input type="range" min="60" max="260" step="10" value={edgeLength} onChange={handleEdgeLengthChange} style={{ width: '90px', cursor: 'pointer' }} />
        </div>
      </div>

      <div style={{ height: '100%', width: '100%', border: '1px solid var(--glass-border)', borderRadius: '4px', overflow: 'hidden', background: 'var(--bg-primary)' }}>
        <CytoscapeComponent
          elements={graphElements}
          layout={{ name: 'null' }}
          style={{ width: '100%', height: '100%' }}
          cy={(cy) => { cyRef.current = cy; }}
          stylesheet={[
            {
              selector: 'node',
              style: {
                'background-opacity': 0.9,
                'background-image-opacity': 1,
                'border-width': 1.5,
                'border-opacity': 0.8,
                'width': nodeSizePx,
                'height': nodeSizePx,
                'label': 'data(label)',
                'color': '#241d14',
                'text-outline-color': '#e9e1cd',
                'text-outline-width': 2,
                'font-size': '11px',
                'font-family': 'IBM Plex Mono, monospace',
                'text-valign': 'bottom',
                'text-margin-y': 8,
                'cursor': 'pointer',
                'transition-property': 'border-width, border-color, width, height',
                'transition-duration': '0.12s',
                'background-position-x': '50%',
                'background-position-y': '50%',
                'background-clip': 'node'
              } as any
            },
            {
              selector: 'node:hover',
              style: {
                'width': nodeSizeHoverPx,
                'height': nodeSizeHoverPx,
              } as any
            },
            {
              selector: 'node:selected',
              style: {
                'width': nodeSizeSelectedPx,
                'height': nodeSizeSelectedPx,
                'border-width': 3
              } as any
            },
            {
              selector: 'node.person, node[type="person"]',
              style: {
                'border-color': '#8a2a24',
                'background-color': '#8a2a24',
                'shape': 'ellipse',
                'background-image': svgPerson,
                'background-width': '52%',
                'background-height': '52%'
              } as any
            },
            {
              selector: 'node.fir, node[type="fir"]',
              style: {
                'border-color': '#2f4a3c',
                'background-color': '#2f4a3c',
                'shape': 'round-rectangle',
                'background-image': svgFir,
                'background-width': '48%',
                'background-height': '48%'
              } as any
            },
            {
              selector: 'node[type="location"]',
              style: {
                'border-color': '#4a5a7a',
                'background-color': '#4a5a7a',
                'shape': 'ellipse',
                'background-image': svgLocation,
                'background-width': '48%',
                'background-height': '48%'
              } as any
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
                'font-size': '9px',
                'font-family': 'IBM Plex Mono, monospace',
                'text-background-opacity': 0.85,
                'text-background-color': '#e9e1cd',
                'text-background-padding': '3px',
                'edge-text-rotation': 'autorotate',
                'text-margin-y': -8
              }
            }
          ]}
        />
      </div>
    </div>
  );
}
