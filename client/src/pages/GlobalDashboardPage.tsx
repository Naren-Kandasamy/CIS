import { useCallback, useState } from 'react';
import { DashboardStats } from '../components/stats';
import { ConversationVolumeChart } from '../components/conversation-volume-chart';
import { ChannelBreakdownChart } from '../components/channel-breakdown-chart';
import { RecentConversations } from '../components/recent-conversations';
import NetworkGraph from '../components/dashboard/NetworkGraph';
import CrimeMap from '../components/dashboard/CrimeMap';
import EntityDrawer, { EntityInlinePanel } from '../components/dashboard/EntityDrawer';
import { useEntityDrawer } from '../hooks/useEntityDrawer';
import type { SelectedEntity } from '../types/entities';

// Global analytics board — a cross-case summary. Restored from the pre-Phase-4
// DashboardPanel, minus the parts that now live per-case:
//   • Key Suspects  -> per-case workspace (KeySuspectsList)
//   • Hypothesis workspace -> per-case corkboard (Phase 5)
// What stays here: incident aggregation stat cards, crime-trend + distribution
// charts, the recent-citations table, the Cytoscape entity-relation network
// (proper Person/FIR/Location node icons) and the Leaflet geospatial map.

export default function GlobalDashboardPage() {
  // Side drawer — table-row clicks
  const { selectedEntity: drawerEntity, openEntity: openDrawer, closeDrawer } = useEntityDrawer();

  // Inline panel — graph node clicks (shown beside the graph)
  const [graphEntity, setGraphEntity] = useState<SelectedEntity | null>(null);
  const openGraphPanel = useCallback((entity: SelectedEntity) => setGraphEntity(entity), []);
  const closeGraphPanel = useCallback(() => setGraphEntity(null), []);

  return (
    <div className="workspace-page animate-fade-in">
      <header className="workspace-head">
        <h1 className="stamp-font">Case Board — Analytics</h1>
        <p>Real-time incident aggregation, geospatial mapping, and graph database entity relation networks.</p>
      </header>

      {/* Top stat cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <DashboardStats />
      </div>

      {/* Trend + distribution */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-4">
        <ConversationVolumeChart className="lg:col-span-3" />
        <ChannelBreakdownChart className="lg:col-span-1" />
      </div>

      {/* Recent citations — full width now that Key Suspects is per-case */}
      <RecentConversations onRowClick={openDrawer} />

      {/* Entity relation network */}
      <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
        <h3 className="dossier-panel-title text-base mb-1">Entity Relation Network</h3>
        <p className="dossier-panel-subtitle text-xs mb-3">
          Click any node to inspect — Cytoscape network model mapping cases, co-accused, and modus operandi.
        </p>
        <div className="flex items-center gap-4 mb-4 dossier-mono" style={{ fontSize: '10px' }}>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-primary)', display: 'inline-block' }} />Person</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, background: 'var(--accent-secondary)', display: 'inline-block' }} />FIR</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-blue)', display: 'inline-block' }} />Location</span>
        </div>

        <div className="graph-split-container">
          <div className={`graph-split-graph ${graphEntity ? 'graph-split-graph--narrow' : ''}`}>
            <NetworkGraph onNodeClick={openGraphPanel} />
          </div>
          <div className={`graph-split-detail ${graphEntity ? 'graph-split-detail--open' : ''}`}>
            <EntityInlinePanel entity={graphEntity} onClose={closeGraphPanel} />
          </div>
        </div>
      </div>

      {/* Geospatial map */}
      <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
        <h3 className="dossier-panel-title text-base mb-1">Geospatial Distribution</h3>
        <p className="dossier-panel-subtitle text-xs mb-4">Leaflet geolocations mapping incident crime scenes.</p>
        <CrimeMap />
      </div>

      <EntityDrawer entity={drawerEntity} onClose={closeDrawer} />
    </div>
  );
}
