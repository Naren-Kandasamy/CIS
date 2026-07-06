import React from 'react';
import { DashboardStats } from '../stats';
import { ConversationVolumeChart } from '../conversation-volume-chart';
import { ChannelBreakdownChart } from '../channel-breakdown-chart';
import { RecentConversations } from '../recent-conversations';
import NetworkGraph from './NetworkGraph';
import CrimeMap from './CrimeMap';

interface DashboardPanelProps {
  visualization?: any;
  evidence?: any[];
}

export default function DashboardPanel({ visualization, evidence }: DashboardPanelProps) {
  return (
    <div className="overflow-y-auto h-full w-full flex flex-col gap-6 bg-background text-foreground animate-fade-in" style={{ padding: '40px' }}>
      <div>
        <h2 className="text-3xl font-bold tracking-tight mb-1 text-foreground">Analytics Dashboard</h2>
        <p className="text-sm text-muted-foreground">Real-time incident aggregation, geospatial mapping, and graph database entity relation networks.</p>
      </div>

      {/* Top Stats Cards (4 Columns) */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <DashboardStats visualization={visualization} />
      </div>

      {/* Charts Grid (3:1 columns ratio) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <ConversationVolumeChart visualization={visualization} className="lg:col-span-3" />
        <ChannelBreakdownChart visualization={visualization} className="lg:col-span-1" />
      </div>

      {/* Citation Table and Custom Suspect List */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <RecentConversations visualization={visualization} evidence={evidence} className="lg:col-span-3" />
        
        {/* Active Suspects Quicklist in efferd Card style */}
        <div className="bg-card border border-border rounded-2xl shadow-sm flex flex-col lg:col-span-1 h-full gap-4" style={{ padding: '28px' }}>
          <div className="flex flex-col h-full">
            <div>
              <h3 className="text-foreground text-lg font-semibold mb-1">Key Suspects</h3>
              <p className="text-xs text-muted-foreground mb-4">Top linked co-accused entities.</p>
            </div>
            <div className="flex-1 flex flex-col justify-between py-2">
              {(visualization?.cytoscape?.elements?.filter((el: any) => el.data?.type === 'person')?.slice(0, 3) || []).length > 0 ? (
                visualization.cytoscape.elements
                  .filter((el: any) => el.data?.type === 'person')
                  .slice(0, 3)
                  .map((suspect: any, idx: number) => (
                    <div key={idx} className="flex items-center gap-4 py-5 border-b border-border last:border-b-0">
                      <div className="w-8 h-8 rounded-full bg-[#ffbf69]/20 border border-[#ff9f1c]/40 text-[#326273] flex items-center justify-center text-xs font-bold font-sans">
                        {suspect.data.label ? suspect.data.label.split(" ").map((n: string) => n[0]).join("") : "S"}
                      </div>
                      <div>
                        <div className="text-sm font-semibold text-foreground">{suspect.data.label}</div>
                        <div className="text-xs text-muted-foreground">Co-Accused • Risk 8.5</div>
                      </div>
                    </div>
                  ))
              ) : (
                [
                  { name: "Ramesh Gowda", role: "Primary Accused" },
                  { name: "Siddesh K.", role: "Conspirator" },
                  { name: "Anand Swamy", role: "Abettor" }
                ].map((s, idx) => (
                  <div key={idx} className="flex items-center gap-4 py-5 border-b border-border last:border-b-0">
                    <div className="w-8 h-8 rounded-full bg-[#ffbf69]/20 border border-[#ff9f1c]/40 text-[#326273] flex items-center justify-center text-xs font-bold font-sans">
                      {s.name.split(" ").map((n: string) => n[0]).join("")}
                    </div>
                    <div>
                      <div className="text-sm font-semibold text-foreground">{s.name}</div>
                      <div className="text-xs text-muted-foreground">{s.role} • Risk 8.5</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Network Graph & Map (2:2 columns ratio) */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="bg-card rounded-2xl border border-border shadow-sm" style={{ padding: '28px' }}>
          <h3 className="text-foreground text-lg font-semibold mb-1">Entity Relation Network</h3>
          <p className="text-xs text-muted-foreground mb-4">Cytoscape network model mapping cases, co-accused, and modus operandi.</p>
          <NetworkGraph elements={visualization?.cytoscape?.elements} />
        </div>
        <div className="bg-card rounded-2xl border border-border shadow-sm" style={{ padding: '28px' }}>
          <h3 className="text-foreground text-lg font-semibold mb-1">Geospatial Distribution</h3>
          <p className="text-xs text-muted-foreground mb-4">Leaflet geolocations mapping incident crime scenes.</p>
          <CrimeMap markers={visualization?.leaflet?.markers} />
        </div>
      </div>
    </div>
  );
}
