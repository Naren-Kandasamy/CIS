import { useCallback, useEffect, useState } from 'react';
import { DashboardStats } from '../components/stats';
import { ConversationVolumeChart } from '../components/conversation-volume-chart';
import { ChannelBreakdownChart } from '../components/channel-breakdown-chart';
import { RecentConversations } from '../components/recent-conversations';
import NetworkGraph from '../components/dashboard/NetworkGraph';
import CrimeMap from '../components/dashboard/CrimeMap';
import EntityDrawer, { EntityInlinePanel } from '../components/dashboard/EntityDrawer';
import { getGlobalGraph } from '../lib/api';
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

  // Officer-wide entity relation network — union across all the caller's cases
  const [graphElements, setGraphElements] = useState<any[]>([]);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [sharedAccused, setSharedAccused] = useState(0);
  const [overviewNote, setOverviewNote] = useState<string | null>(null);

  useEffect(() => {
    let live = true;
    getGlobalGraph()
      .then((r) => {
        if (!live) return;
        setGraphElements(r.elements ?? []);
        setSharedAccused(r.shared_accused_count ?? 0);
        setOverviewNote(r.overview ? r.overview_note ?? null : null);
      })
      .catch(() => {
        if (live) setGraphElements([]);
      })
      .finally(() => {
        if (live) setGraphLoaded(true);
      });
    return () => {
      live = false;
    };
  }, []);

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

      {/* Entity relation network — union across every case the officer works */}
      <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
        <h3 className="dossier-panel-title text-base mb-1">Entity Relation Network</h3>
        <p className="dossier-panel-subtitle text-xs mb-3">
          Every case you work, unioned — Accused, victims and districts linked to the FIRs you've
          pinned, hypothesised on, or queried.
          {sharedAccused > 0 && (
            <>
              {' '}
              <strong style={{ color: 'var(--accent-gold)' }}>
                {sharedAccused} accused span more than one case
              </strong>{' '}
              (gold ring).
            </>
          )}
        </p>
        {overviewNote && (
          <p className="dossier-panel-subtitle text-xs mb-3" style={{ fontStyle: 'italic', color: 'var(--text-tertiary)' }}>
            {overviewNote}
          </p>
        )}
        <div className="flex items-center gap-4 mb-4 dossier-mono flex-wrap" style={{ fontSize: '10px' }}>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-primary)', display: 'inline-block' }} />Accused</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, background: 'var(--accent-secondary)', display: 'inline-block' }} />FIR</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-blue)', display: 'inline-block' }} />Location</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: 'var(--accent-gold)', display: 'inline-block' }} />Victim</span>
        </div>

        <div className="graph-split-container">
          <div className={`graph-split-graph ${graphEntity ? 'graph-split-graph--narrow' : ''}`}>
            <NetworkGraph
              elements={graphElements}
              onNodeClick={openGraphPanel}
              fallbackToDemo={false}
              emptyLabel={
                graphLoaded
                  ? 'Nothing linked yet — pin FIRs to your cases and the network fills in.'
                  : 'Loading the network…'
              }
            />
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
