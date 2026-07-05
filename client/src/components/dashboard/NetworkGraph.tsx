import React from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
interface NetworkGraphProps {
  elements?: any[];
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

export default function NetworkGraph({ elements }: NetworkGraphProps) {
  // Use provided elements or default to mockup data if none provided
  const graphElements = elements && elements.length > 0 ? elements : DEFAULT_ELEMENTS;

  return (
    <div style={{ height: '400px', width: '100%', padding: '8px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '15px', fontWeight: '500' }}>Entity Network</h3>
      <div style={{ height: 'calc(100% - 40px)', width: '100%', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', overflow: 'hidden' }}>
        <CytoscapeComponent 
          elements={graphElements} 
          layout={{ name: 'cose' }}
          style={{ width: '100%', height: '100%' }}
          stylesheet={[
            {
              selector: 'node',
              style: {
                'background-color': '#4287f5',
                'label': 'data(label)',
                'color': '#fff',
                'text-outline-color': '#222',
                'text-outline-width': 2,
                'font-size': '12px'
              }
            },
            {
              selector: 'node.person',
              style: {
                'background-color': '#f54242',
                'shape': 'ellipse'
              }
            },
            {
              selector: 'node.fir',
              style: {
                'background-color': '#42f569',
                'shape': 'rectangle'
              }
            },
            {
              selector: 'edge',
              style: {
                'width': 2,
                'line-color': '#555',
                'target-arrow-color': '#555',
                'target-arrow-shape': 'triangle',
                'curve-style': 'bezier',
                'label': 'data(label)',
                'color': '#aaa',
                'font-size': '10px',
                'text-background-opacity': 1,
                'text-background-color': '#222',
                'text-background-padding': '2px'
              }
            }
          ]}
        />
      </div>
    </div>
  );
}
