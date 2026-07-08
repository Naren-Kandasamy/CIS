import React, { useState, useCallback } from 'react';
import { DashboardStats } from '../stats';
import { ConversationVolumeChart } from '../conversation-volume-chart';
import { ChannelBreakdownChart } from '../channel-breakdown-chart';
import { RecentConversations } from '../recent-conversations';
import NetworkGraph from './NetworkGraph';
import CrimeMap from './CrimeMap';
import EntityDrawer, { EntityInlinePanel } from './EntityDrawer';
import { useEntityDrawer, resolveLinkedNodes, matchEvidenceByFirId } from '../../hooks/useEntityDrawer';
import type { SelectedEntity } from '../../hooks/useEntityDrawer';

interface DashboardPanelProps {
  visualization?: any;
  evidence?: any[];
}

export default function DashboardPanel({ visualization, evidence }: DashboardPanelProps) {
  // Side drawer — for table rows and suspect list clicks
  const { selectedEntity: drawerEntity, openEntity: openDrawer, closeDrawer } = useEntityDrawer();

  // Inline panel — for graph node clicks (shown right beside the graph)
  const [graphEntity, setGraphEntity] = useState<SelectedEntity | null>(null);
  const openGraphPanel = useCallback((entity: SelectedEntity) => setGraphEntity(entity), []);
  const closeGraphPanel = useCallback(() => setGraphEntity(null), []);

  const cyElements = visualization?.cytoscape?.elements ?? [];

  /** Build a SelectedEntity for a person node from the suspect list */
  function buildPersonEntity(suspect: any): SelectedEntity {
    const nodeId: string = suspect.data.id;
    const linkedNodes = resolveLinkedNodes(nodeId, cyElements);
    const evidenceItems: any[] = [];
    for (const ln of linkedNodes.filter(n => n.type === 'fir')) {
      evidenceItems.push(...matchEvidenceByFirId(ln.id, evidence ?? []));
    }
    return {
      type: 'person',
      id: nodeId,
      label: suspect.data.label ?? nodeId,
      data: suspect.data,
      linkedNodes,
      evidenceItems,
    };
  }

  return (
    <div className="overflow-y-auto h-full w-full flex flex-col gap-6 animate-fade-in" style={{ padding: '40px', color: 'var(--text-primary)' }}>
      <div style={{ borderBottom: '1px dashed var(--glass-border)', paddingBottom: '16px' }}>
        <h2 className="stamp-font text-2xl mb-1" style={{ color: 'var(--text-primary)' }}>Case Board — Analytics</h2>
        <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>Real-time incident aggregation, geospatial mapping, and graph database entity relation networks.</p>
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
        <RecentConversations
          visualization={visualization}
          evidence={evidence}
          onRowClick={openDrawer}
          className="lg:col-span-3"
        />

        {/* Active Suspects Quicklist */}
        <div className="dossier-panel dossier-paperclip flex flex-col lg:col-span-1 justify-between h-auto gap-4" style={{ padding: '20px' }}>
          <div>
            <h3 className="dossier-panel-title text-base mb-1">Key Suspects</h3>
            <p className="dossier-panel-subtitle text-xs mb-4">Top linked co-accused entities.</p>
            <div className="space-y-3">
              {(visualization?.cytoscape?.elements?.filter((el: any) => el.data?.type === 'person')?.slice(0, 3) || []).length > 0 ? (
                visualization.cytoscape.elements
                  .filter((el: any) => el.data?.type === 'person')
                  .slice(0, 3)
                  .map((suspect: any, idx: number) => (
                    <button
                      key={idx}
                      type="button"
                      className="flex items-center gap-3 py-1 pb-2 w-full text-left entity-clickable"
                      style={{ background: 'transparent', border: 'none', borderBottom: '1px dashed var(--paper-line)', cursor: 'pointer' }}
                      onClick={() => openDrawer(buildPersonEntity(suspect))}
                      aria-label={`View details for ${suspect.data.label}`}
                    >
                      <div className="dossier-avatar w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold flex-shrink-0">
                        {suspect.data.label ? suspect.data.label.split(" ").map((n: string) => n[0]).join("") : "S"}
                      </div>
                      <div>
                        <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{suspect.data.label}</div>
                        <div className="dossier-mono text-xs">Co-accused · Risk 8.5</div>
                      </div>
                    </button>
                  ))
              ) : (
                [
                  { name: "Ramesh Gowda", role: "Primary Accused" },
                  { name: "Siddesh K.", role: "Conspirator" },
                  { name: "Anand Swamy", role: "Abettor" }
                ].map((s, idx) => (
                  <div key={idx} className="flex items-center gap-3 py-1 pb-2" style={{ borderBottom: '1px dashed var(--paper-line)' }}>
                    <div className="dossier-avatar w-8 h-8 rounded-full flex items-center justify-center text-xs font-semibold">
                      {s.name.split(" ").map((n: string) => n[0]).join("")}
                    </div>
                    <div>
                      <div className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>{s.name}</div>
                      <div className="dossier-mono text-xs">{s.role} · Risk 8.5</div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Network Graph & Map — graph node clicks show inline panel right beside the graph */}
      <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
        <h3 className="dossier-panel-title text-base mb-1">Entity Relation Network</h3>
        <p className="dossier-panel-subtitle text-xs mb-3">
          Click any node to inspect — Cytoscape network model mapping cases, co-accused, and modus operandi.
        </p>
        <div className="flex items-center gap-4 mb-4 dossier-mono" style={{ fontSize: '10px' }}>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: '#8a2a24', display: 'inline-block' }} />Person</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, background: '#2f4a3c', display: 'inline-block' }} />FIR</span>
          <span className="flex items-center gap-1.5"><span style={{ width: 8, height: 8, borderRadius: '50%', background: '#4a5a7a', display: 'inline-block' }} />Location</span>
        </div>

        {/* Split layout: graph always left, entity detail slides in right when a node is clicked */}
        <div className="graph-split-container">
          <div className={`graph-split-graph ${graphEntity ? 'graph-split-graph--narrow' : ''}`}>
            <NetworkGraph
              elements={visualization?.cytoscape?.elements}
              onNodeClick={openGraphPanel}
              evidence={evidence}
            />
          </div>
          <div className={`graph-split-detail ${graphEntity ? 'graph-split-detail--open' : ''}`}>
            <EntityInlinePanel entity={graphEntity} onClose={closeGraphPanel} />
          </div>
        </div>
      </div>

      {/* Crime Map in its own card below */}
      <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
        <h3 className="dossier-panel-title text-base mb-1">Geospatial Distribution</h3>
        <p className="dossier-panel-subtitle text-xs mb-4">Leaflet geolocations mapping incident crime scenes.</p>
        <CrimeMap markers={visualization?.leaflet?.markers} />
      </div>

      {/* Side drawer — only for table row / suspect list triggers */}
      <EntityDrawer entity={drawerEntity} onClose={closeDrawer} />
    </div>
  );
}
