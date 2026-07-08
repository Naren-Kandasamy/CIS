import React, { useEffect, useRef } from 'react';
import { X, User, FolderOpen, MapPin, AlertTriangle, Link2, FileText, Calendar, Shield } from 'lucide-react';
import type { SelectedEntity, LinkedNode } from '../../hooks/useEntityDrawer';

interface EntityDrawerProps {
  entity: SelectedEntity | null;
  onClose: () => void;
}

// ─── Icon + colour per entity type ────────────────────────────────────────────

function entityMeta(type: string) {
  switch (type) {
    case 'person':
      return { Icon: User, accent: 'var(--accent-primary)', label: 'PERSON OF INTEREST' };
    case 'fir':
      return { Icon: FolderOpen, accent: 'var(--accent-secondary)', label: 'CASE FILE' };
    case 'location':
      return { Icon: MapPin, accent: 'var(--accent-gold)', label: 'LOCATION' };
    default:
      return { Icon: FileText, accent: 'var(--text-tertiary)', label: type.toUpperCase() };
  }
}

// ─── Section component ─────────────────────────────────────────────────────────

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="entity-drawer-section">
      <div className="entity-drawer-section-title">{title}</div>
      {children}
    </div>
  );
}

// ─── Linked node chips ─────────────────────────────────────────────────────────

function NodeChip({ node, onClick }: { node: LinkedNode; onClick?: (n: LinkedNode) => void }) {
  const { Icon, accent } = entityMeta(node.type);
  return (
    <button
      type="button"
      className="entity-node-chip"
      onClick={() => onClick?.(node)}
      title={node.edgeLabel ? `Relationship: ${node.edgeLabel}` : undefined}
      aria-label={`View ${node.label}`}
    >
      <Icon size={11} style={{ color: accent, flexShrink: 0 }} />
      <span className="entity-node-chip-label">{node.label}</span>
      {node.edgeLabel && <span className="entity-node-chip-rel">{node.edgeLabel}</span>}
    </button>
  );
}

// ─── Field row ─────────────────────────────────────────────────────────────────

function Field({ label, value }: { label: string; value?: string | number | null }) {
  if (value === undefined || value === null || value === '' || value === 'N/A') return null;
  return (
    <div className="entity-field-row">
      <span className="entity-field-label">{label}</span>
      <span className="entity-field-value">{String(value)}</span>
    </div>
  );
}

// ─── Confidence badge ──────────────────────────────────────────────────────────

function ConfidenceBadge({ level }: { level: string }) {
  const lc = level?.toLowerCase();
  const color =
    lc === 'high' ? '#2f4a3c' :
    lc === 'medium' ? '#a9791f' :
    '#8a2a24';
  return (
    <span
      className="entity-confidence-badge"
      style={{ borderColor: color, color }}
    >
      {level.toUpperCase()}
    </span>
  );
}

// ─── Person detail view ────────────────────────────────────────────────────────

function PersonDetail({ entity }: { entity: SelectedEntity }) {
  const d = entity.data ?? {};
  const linkedFIRs = entity.linkedNodes?.filter(n => n.type === 'fir') ?? [];
  const coAccused = entity.linkedNodes?.filter(n => n.type === 'person') ?? [];

  const priorCount = d.prior_fir_count ?? linkedFIRs.length;
  const riskLevel = priorCount >= 5 ? 'HIGH' : priorCount >= 2 ? 'MEDIUM' : 'LOW';
  const riskColor = riskLevel === 'HIGH' ? '#8a2a24' : riskLevel === 'MEDIUM' ? '#a9791f' : '#2f4a3c';

  return (
    <>
      {/* Risk banner */}
      <div className="entity-risk-banner" style={{ borderColor: riskColor, background: `${riskColor}12` }}>
        <AlertTriangle size={13} style={{ color: riskColor }} />
        <span style={{ color: riskColor, fontFamily: 'IBM Plex Mono, monospace', fontSize: '11px', fontWeight: 600 }}>
          RISK LEVEL: {riskLevel}
        </span>
        <span style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginLeft: 'auto' }}>
          {priorCount} linked FIR{priorCount !== 1 ? 's' : ''}
        </span>
      </div>

      <Section title="IDENTITY">
        <Field label="Full Name" value={d.name ?? entity.label} />
        <Field label="Sort Label" value={d.sort_label} />
        <Field label="Age" value={d.age_years ? `${d.age_years} yrs` : undefined} />
        <Field label="Gender" value={d.gender_id} />
        {d.aliases && d.aliases.length > 0 && (
          <div className="entity-field-row">
            <span className="entity-field-label">Aliases</span>
            <span className="entity-field-value" style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
              {(Array.isArray(d.aliases) ? d.aliases : [d.aliases]).map((a: string, i: number) => (
                <span key={i} className="entity-tag">{a}</span>
              ))}
            </span>
          </div>
        )}
        {d.tattoos && d.tattoos.length > 0 && (
          <Field label="Tattoos" value={Array.isArray(d.tattoos) ? d.tattoos.join(', ') : d.tattoos} />
        )}
        <Field label="Primary Accused" value={d.is_primary_accused !== undefined ? (d.is_primary_accused ? 'Yes' : 'No') : undefined} />
        <Field label="Prior FIR Count" value={d.prior_fir_count} />
      </Section>

      {linkedFIRs.length > 0 && (
        <Section title={`LINKED CASES (${linkedFIRs.length})`}>
          <div className="entity-chip-grid">
            {linkedFIRs.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
          {/* Show evidence detail if available */}
          {entity.evidenceItems && entity.evidenceItems.length > 0 && (
            <div className="entity-evidence-list">
              {entity.evidenceItems.slice(0, 3).map((ev, i) => (
                <div key={i} className="entity-evidence-row">
                  <span className="dossier-id" style={{ fontSize: '11px' }}>{ev.fir_id}</span>
                  {ev.data?.crime_type && <span className="entity-tag">{ev.data.crime_type}</span>}
                  {ev.data?.Date && <span style={{ color: 'var(--text-tertiary)', fontSize: '11px', marginLeft: 'auto', fontFamily: 'IBM Plex Mono, monospace' }}>{ev.data.Date}</span>}
                  {ev.confidence && <ConfidenceBadge level={ev.confidence} />}
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {coAccused.length > 0 && (
        <Section title={`CO-ACCUSED / ASSOCIATES (${coAccused.length})`}>
          <div className="entity-chip-grid">
            {coAccused.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

// ─── FIR detail view ───────────────────────────────────────────────────────────

function FIRDetail({ entity }: { entity: SelectedEntity }) {
  const d = entity.data ?? {};
  const ev = entity.evidenceItems?.[0];
  const evData = ev?.data ?? {};

  const crimeType = d.crime_type ?? evData.crime_type ?? evData.crime_category ?? '';
  const district = d.district ?? evData.district ?? '';
  const date = d.date ?? evData.Date ?? evData.date ?? evData.occurrence_date ?? '';
  const weapon = d.weapon ?? evData.weapon ?? evData.weapon_used ?? '';
  const narrative = d.narrative ?? evData.narrative ?? '';
  const moDescriptor = d.modus_operandi ?? evData.mo_descriptor ?? '';
  const psName = d.ps_name ?? evData.ps_name ?? '';

  const persons = entity.linkedNodes?.filter(n => n.type === 'person') ?? [];
  const locations = entity.linkedNodes?.filter(n => n.type === 'location') ?? [];

  return (
    <>
      <Section title="CASE DETAILS">
        <Field label="Crime No" value={d.crime_no ?? entity.id} />
        <Field label="Registered Date" value={date} />
        <Field label="Crime Type" value={crimeType} />
        <Field label="District" value={district} />
        <Field label="Police Station" value={psName} />
        <Field label="Weapon" value={weapon || 'None'} />
        <Field label="Status" value={d.status} />
        {ev?.confidence && (
          <div className="entity-field-row">
            <span className="entity-field-label">Evidence Confidence</span>
            <ConfidenceBadge level={ev.confidence} />
          </div>
        )}
      </Section>

      {moDescriptor && (
        <Section title="MODUS OPERANDI">
          <p className="entity-narrative">{moDescriptor}</p>
        </Section>
      )}

      {narrative && (
        <Section title="NARRATIVE">
          <p className="entity-narrative">{narrative}</p>
        </Section>
      )}

      {persons.length > 0 && (
        <Section title={`ACCUSED / PERSONS (${persons.length})`}>
          <div className="entity-chip-grid">
            {persons.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
        </Section>
      )}

      {locations.length > 0 && (
        <Section title="LOCATIONS">
          <div className="entity-chip-grid">
            {locations.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

// ─── Location detail view ──────────────────────────────────────────────────────

function LocationDetail({ entity }: { entity: SelectedEntity }) {
  const linkedFIRs = entity.linkedNodes?.filter(n => n.type === 'fir') ?? [];
  const linkedPersons = entity.linkedNodes?.filter(n => n.type === 'person') ?? [];

  // Count crime types from evidence items
  const crimeBreakdown: Record<string, number> = {};
  for (const ev of entity.evidenceItems ?? []) {
    const ct = ev.data?.crime_type ?? ev.data?.crime_category ?? 'Unknown';
    crimeBreakdown[ct] = (crimeBreakdown[ct] ?? 0) + 1;
  }
  const crimeEntries = Object.entries(crimeBreakdown).sort((a, b) => b[1] - a[1]);

  return (
    <>
      <Section title="LOCATION INFO">
        <Field label="Name" value={entity.label} />
        <Field label="FIRs Filed Here" value={linkedFIRs.length || undefined} />
        <Field label="Persons Linked" value={linkedPersons.length || undefined} />
      </Section>

      {crimeEntries.length > 0 && (
        <Section title="CRIME BREAKDOWN">
          {crimeEntries.map(([type, count]) => (
            <div key={type} className="entity-field-row">
              <span className="entity-field-label">{type}</span>
              <span className="entity-field-value" style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                <span className="entity-tag">{count} case{count !== 1 ? 's' : ''}</span>
              </span>
            </div>
          ))}
        </Section>
      )}

      {linkedFIRs.length > 0 && (
        <Section title={`INCIDENTS (${linkedFIRs.length})`}>
          <div className="entity-chip-grid">
            {linkedFIRs.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
        </Section>
      )}

      {linkedPersons.length > 0 && (
        <Section title="LINKED PERSONS">
          <div className="entity-chip-grid">
            {linkedPersons.map((n) => (
              <NodeChip key={n.id} node={n} />
            ))}
          </div>
        </Section>
      )}
    </>
  );
}

// ─── Shared detail body (used by both drawer and inline panel) ────────────────

export function EntityDetailContent({ entity, onClose }: { entity: SelectedEntity; onClose: () => void }) {
  const { Icon, accent, label } = entityMeta(entity.type);

  return (
    <>
      {/* Header */}
      <div className="entity-drawer-header">
        <div className="entity-drawer-header-left">
          <div className="entity-drawer-type-badge" style={{ borderColor: accent, background: `${accent}18` }}>
            <Icon size={13} style={{ color: accent }} />
            <span style={{ color: accent, fontSize: '10px', fontFamily: 'IBM Plex Mono, monospace', fontWeight: 700, letterSpacing: '0.1em' }}>
              {label}
            </span>
          </div>
          <h2 className="entity-drawer-title">{entity.label}</h2>
          <span className="entity-drawer-id dossier-mono">{entity.id}</span>
        </div>
        <button
          type="button"
          className="entity-drawer-close"
          onClick={onClose}
          aria-label="Close entity detail"
        >
          <X size={16} />
        </button>
      </div>

      {/* Scrollable body */}
      <div className="entity-drawer-body">
        {entity.type === 'person' && <PersonDetail entity={entity} />}
        {entity.type === 'fir' && <FIRDetail entity={entity} />}
        {entity.type === 'location' && <LocationDetail entity={entity} />}
        {!['person', 'fir', 'location'].includes(entity.type) && (
          <Section title="RAW DATA">
            <pre style={{ fontSize: '10px', color: 'var(--text-secondary)', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
              {JSON.stringify(entity.data ?? {}, null, 2)}
            </pre>
          </Section>
        )}
      </div>

      {/* Footer stamp */}
      <div className="entity-drawer-footer">
        <Link2 size={11} style={{ color: 'var(--text-tertiary)' }} />
        <span>
          {entity.linkedNodes?.length ?? 0} linked node{entity.linkedNodes?.length !== 1 ? 's' : ''} · {entity.evidenceItems?.length ?? 0} evidence item{entity.evidenceItems?.length !== 1 ? 's' : ''}
        </span>
      </div>
    </>
  );
}

// ─── Inline panel — sits beside the graph, no overlay ─────────────────────────

export function EntityInlinePanel({ entity, onClose }: { entity: SelectedEntity | null; onClose: () => void }) {
  if (!entity) return null;
  return (
    <div className="entity-inline-panel animate-fade-in">
      <EntityDetailContent entity={entity} onClose={onClose} />
    </div>
  );
}

// ─── Main side drawer — fixed overlay, for table / evidence card triggers ──────

export default function EntityDrawer({ entity, onClose }: EntityDrawerProps) {
  const isOpen = entity !== null;

  // Close on Escape
  useEffect(() => {
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isOpen) onClose();
    };
    window.addEventListener('keydown', handleKey);
    return () => window.removeEventListener('keydown', handleKey);
  }, [isOpen, onClose]);

  return (
    <>
      {/* Backdrop */}
      <div
        className={`entity-drawer-overlay ${isOpen ? 'entity-drawer-overlay--open' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Drawer panel */}
      <aside
        className={`entity-drawer ${isOpen ? 'entity-drawer--open' : ''}`}
        aria-label="Entity Detail Drawer"
        role="complementary"
      >
        {entity && <EntityDetailContent entity={entity} onClose={onClose} />}
      </aside>
    </>
  );
}
