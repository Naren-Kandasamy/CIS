import React from 'react';
import { PieChart, Pie, Cell, Tooltip, ResponsiveContainer, Legend } from 'recharts';

const DEFAULT_DATA = [
  { name: 'Theft', value: 400 },
  { name: 'Assault', value: 300 },
  { name: 'Fraud', value: 300 },
  { name: 'Burglary', value: 200 },
];

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#AF19FF', '#FF19A3'];

interface DonutChartProps {
  data?: { name: string, value: number }[];
}

export default function DonutChart({ data }: DonutChartProps) {
  const chartData = data && data.length > 0 ? data : DEFAULT_DATA;
  
  return (
    <div style={{ height: '300px', width: '100%', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', padding: '16px', boxSizing: 'border-box' }}>
      <h3 style={{ color: 'white', marginBottom: '16px', fontSize: '16px', fontWeight: '500' }}>Crime Distribution</h3>
      <ResponsiveContainer width="100%" height="80%">
        <PieChart>
          <Pie
            data={chartData}
            innerRadius={60}
            outerRadius={80}
            paddingAngle={5}
            dataKey="value"
            stroke="none"
            label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
            labelLine={true}
          >
            {chartData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip contentStyle={{ backgroundColor: '#222', border: '1px solid #444', borderRadius: '8px', color: '#fff' }} />
          <Legend verticalAlign="bottom" height={36} iconType="circle" wrapperStyle={{ fontSize: '12px' }} />
        </PieChart>
      </ResponsiveContainer>
    </div>
  );
}
