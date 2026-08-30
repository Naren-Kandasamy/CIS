import { useCallback, useEffect, useMemo, useState } from 'react';
import type { PinnedItem } from '../../types/board';
import type { SelectedEntity } from '../../types/entities';
import { getCaseGraph } from '../../lib/api';
import NetworkGraph from '../dashboard/NetworkGraph';
import CrimeMap from '../dashboard/CrimeMap';
import { EntityInlinePanel } from '../dashboard/EntityDrawer';

// The per-case Entity Relation Network now comes from the graph DB via
// GET /api/cases/:id/graph (FIRs the case touches -> their Accused / Victim /
// district). The map still derives its markers client-side from pinned citation
// lat/long, which the graph endpoint doesn't carry.

function toNum(v: unknown): number | null {
  const n = typeof v === 'string' ? parseFloat(v) : (v as number);
  return typeof n === 'number' && !Number.isNaN(n) ? n : null;
}

function deriveMarkers(citations: PinnedItem[]): { position: [number, number]; popup: string }[] {
  const markers: { position: [number, number]; popup: string }[] = [];
  citations.forEach((pin, i) => {
    const c = pin.content as Record<string, any>;
    const d = (c.data as Record<string, any>) ?? {};
    const lat = toNum(d.latitude ?? d.lat);
    const lng = toNum(d.longitude ?? d.lng ?? d.lon);
    if (lat != null && lng != null) {
      const firId = String(c.fir_id ?? d.crime_no ?? `fir-${i}`);
      markers.push({
        position: [lat, lng],
        popup: `${d.crime_no ?? firId}${d.district ? ` · ${d.district}` : ''}`,
      });
    }
  });
  return markers;
}

export function WorkspaceGraphs({
  caseId,
  citations,
  suspects: _suspects,
}: {
  caseId: string;
  citations: PinnedItem[];
  suspects: PinnedItem[];
}) {
  const markers = useMemo(() => deriveMarkers(citations), [citations]);

  const [elements, setElements] = useState<any[]>([]);
  const [graphLoaded, setGraphLoaded] = useState(false);
  const [graphEntity, setGraphEntity] = useState<SelectedEntity | null>(null);
  const closePanel = useCallback(() => setGraphEntity(null), []);

  useEffect(() => {
    let live = true;
    setGraphLoaded(false);
    getCaseGraph(caseId)
      .then((r) => {
        if (live) setElements(r.elements ?? []);
      })
      .catch(() => {
        if (live) setElements([]);
      })
      .finally(() => {
        if (live) setGraphLoaded(true);
      });
    return () => {
      live = false;
    };
  }, [caseId]);

  const showNetwork = !graphLoaded || elements.length > 0;

  return (
    <>
      {showNetwork && (
        <div className="dossier-panel dossier-paperclip" style={{ padding: '28px' }}>
          <h3 className="dossier-panel-title text-base mb-1">Entity Relation Network</h3>
          <p className="dossier-panel-subtitle text-xs mb-3">
            Accused, victims and locations linked to the FIRs this case has pinned,
            hypothesised on, or queried. Click a node to inspect.
          </p>
          <div className="graph-split-container">
            <div className={`graph-split-graph ${graphEntity ? 'graph-split-graph--narrow' : ''}`}>
              <NetworkGraph
                elements={elements}
                onNodeClick={setGraphEntity}
                fallbackToDemo={false}
                emptyLabel={
                  graphLoaded
                    ? 'No accused or victims linked to this case’s FIRs in the graph yet.'
                    : 'Loading the network…'
                }
              />
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
