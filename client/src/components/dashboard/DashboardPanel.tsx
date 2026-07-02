import React from 'react';
import NetworkGraph from './NetworkGraph';
import CrimeMap from './CrimeMap';
import TrendChart from './TrendChart';
import DonutChart from './DonutChart';

interface DashboardPanelProps {
  visualization?: any;
}

export default function DashboardPanel({ visualization }: DashboardPanelProps) {
  return (
    <div style={{ padding: '24px', overflowY: 'auto', height: '100%', boxSizing: 'border-box', width: '100%' }}>
      <h2 style={{ color: 'white', marginBottom: '24px', fontSize: '24px', fontWeight: 600 }}>Analytics Dashboard</h2>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <TrendChart data={visualization?.recharts?.trend} />
        <DonutChart data={visualization?.recharts?.donut} />
      </div>
      
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px', marginBottom: '24px' }}>
        <NetworkGraph elements={visualization?.cytoscape?.elements} />
        <CrimeMap markers={visualization?.leaflet?.markers} />
      </div>
    </div>
  );
}
