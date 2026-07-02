import React from 'react';
import CytoscapeComponent from 'react-cytoscapejs';
interface NetworkGraphProps {
  elements?: any[];
}

export default function NetworkGraph({ elements }: NetworkGraphProps) {
  // Use provided elements or default to empty if none provided
  const graphElements = elements && elements.length > 0 ? elements : [];

  return (
    <div style={{ height: '400px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '16px', fontWeight: '500' }}>Entity Network</h3>
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
