import React from 'react';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';

const DEFAULT_DATA = [
  { name: 'Jan', crimes: 40 },
  { name: 'Feb', crimes: 30 },
  { name: 'Mar', crimes: 20 },
  { name: 'Apr', crimes: 27 },
  { name: 'May', crimes: 18 },
  { name: 'Jun', crimes: 23 },
  { name: 'Jul', crimes: 34 },
];

interface TrendChartProps {
  data?: { name: string, crimes: number }[];
}

export default function TrendChart({ data }: TrendChartProps) {
  const chartData = data && data.length > 0 ? data : DEFAULT_DATA;
  return (
    <div style={{ height: '300px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '16px', fontWeight: '500' }}>Crime Trends (Last 7 Months)</h3>
      <ResponsiveContainer width="100%" height="80%">
        <LineChart data={chartData}>
          <CartesianGrid strokeDasharray="3 3" stroke="#444" />
          <XAxis dataKey="name" stroke="#888" fontSize={12} />
          <YAxis stroke="#888" fontSize={12} />
          <Tooltip contentStyle={{ backgroundColor: '#222', border: '1px solid #444', borderRadius: '8px', color: '#fff' }} />
          <Line type="monotone" dataKey="crimes" stroke="#8884d8" strokeWidth={3} dot={{ r: 4, fill: '#8884d8' }} activeDot={{ r: 6 }} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
