import { useMemo, useState, useCallback } from 'react';
import type { PinnedItem } from '../../types/board';
import type { SelectedEntity } from '../../types/entities';
import NetworkGraph from '../dashboard/NetworkGraph';
import CrimeMap from '../dashboard/CrimeMap';
import { EntityInlinePanel } from '../dashboard/EntityDrawer';

// Phase 4: NetworkGraph + CrimeMap for the case, derived CLIENT-SIDE from pinned
// citation/suspect content (v1 — a real GET /api/cases/:id/graph unioning
// session visualizations is a documented follow-up). Only mounts a view when it
// has real derived data, so the components' demo fallbacks never show.

interface Derived {
  elements: any[];
  markers: { position: [number, number]; popup: string }[];
}

function toNum(v: unknown): number | null {
  const n = typeof v === 'string' ? parseFloat(v) : (v as number);
  return typeof n === 'number' && !Number.isNaN(n) ? n : null;
}

function derive(citations: PinnedItem[], suspects: PinnedItem[]): Derived {
  const elements: any[] = [];
  const markers: Derived['markers'] = [];
  const seen = new Set<string>();

  const addNode = (id: string, label: string, type: string) => {
    if (!id || seen.has(id)) return;
    seen.add(id);
    elements.push({ data: { id, label, type }, classes: type });
  };

  citations.forEach((pin, i) => {
    const c = pin.content as Record<string, any>;
    const d = (c.data as Record<string, any>) ?? {};
    const firId = String(c.fir_id ?? d.crime_no ?? `fir-${i}`);
    addNode(firId, String(d.crime_no ?? c.fir_id ?? firId), 'fir');

    const lat = toNum(d.latitude ?? d.lat);
    const lng = toNum(d.longitude ?? d.lng ?? d.lon);
    if (lat != null && lng != null) {
      markers.push({
        position: [lat, lng],
        popup: `${d.crime_no ?? firId}${d.district ? ` · ${d.district}` : ''}`,
      });
    }

    const accused: unknown = d.accused_ids ?? d.accused ?? d.accused_names;
    const list = Array.isArray(accused)
      ? accused
      : typeof accused === 'string'
        ? accused.split(/[,;]/).map((s) => s.trim()).filter(Boolean)
        : [];
    list.forEach((a: string) => {
      const pid = String(a);
      addNode(pid, pid, 'person');
      elements.push({ data: { source: pid, target: firId, label: 'Accused' } });
    });
  });

  suspects.forEach((pin, i) => {
    const c = pin.content as Record<string, any>;
    const id = String(c.id ?? c.label ?? c.name ?? `person-${i}`);
    addNode(id, String(c.label ?? c.name ?? id), 'person');
  });

  return { elements, markers };
}

export function WorkspaceGraphs({
  citations,
  suspects,
}: {
  citations: PinnedItem[];
  suspects: PinnedItem[];
}) {
  const { elements, markers } = useMemo(
    () => derive(citations, suspects),
    [citations, suspects],
  );
  const [graphEntity, setGraphEntity] = useState<SelectedEntity | null>(null);
  const closePanel = useCallback(() => setGraphEntity(null), []);

  if (elements.length === 0 && markers.length === 0) return null;

  return (
    <>
      {elements.length > 0 && (
        <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
          <h3 className="dossier-panel-title text-base mb-1">Entity Relation Network</h3>
          <p className="dossier-panel-subtitle text-xs mb-3">
            Derived from pinned FIRs and suspects. Click a node to inspect.
          </p>
          <div className="graph-split-container">
            <div className={`graph-split-graph ${graphEntity ? 'graph-split-graph--narrow' : ''}`}>
              <NetworkGraph elements={elements} onNodeClick={setGraphEntity} />
            </div>
            <div className={`graph-split-detail ${graphEntity ? 'graph-split-detail--open' : ''}`}>
              <EntityInlinePanel entity={graphEntity} onClose={closePanel} />
            </div>
          </div>
        </div>
      )}

      {markers.length > 0 && (
        <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
          <h3 className="dossier-panel-title text-base mb-1">Geospatial Distribution</h3>
          <p className="dossier-panel-subtitle text-xs mb-4">
            Incident locations from pinned citations.
          </p>
          <CrimeMap markers={markers} />
        </div>
      )}
    </>
  );
}
