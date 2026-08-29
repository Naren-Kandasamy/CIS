import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, PointerEvent as ReactPointerEvent } from 'react';
import type { BoardCard, PinnedItem } from '../../types/board';
import type { HypothesisRecord } from '../../types/hypothesis';
import { useBoardStore } from '../../stores/boardStore';
import { useEntityStore } from '../../stores/entityStore';
import { useHypotheses } from '../../hooks/useHypotheses';
import { BoardCardFrame } from './BoardCardFrame';
import { BoardToolbar } from './BoardToolbar';
import { YarnLayer, type YarnEdge } from './YarnLayer';
import { HypothesisNoteCard } from './HypothesisNoteCard';
import { SuspectTile } from './SuspectTile';
import { FirCard } from './FirCard';
import { FreeNoteCard } from './FreeNoteCard';

// The freeform board. A single pan/zoom transform on `.corkboard-surface`;
// cards are absolutely positioned in board coordinates; the yarn layer draws
// sagging beziers between the centres of corded cards. Layout edits are applied
// locally at once and flushed to case_board_layout on an 800ms debounce.

interface View {
  x: number;
  y: number;
  k: number;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const jitter = () => Math.random() * 8 - 4;

function fallbackPin(card: BoardCard): PinnedItem {
  return {
    pinned_by: '',
    pinned_at: 0,
    source_session_id: '',
    content_type: card.kind,
    content: { id: card.refId, label: card.refId ?? card.id },
  };
}

interface Props {
  caseId: string;
  cards: BoardCard[];
  hypotheses: HypothesisRecord[];
}

export function CorkboardCanvas({ caseId, cards, hypotheses }: Props) {
  const upsertCard = useBoardStore((s) => s.upsertCard);
  const patchCard = useBoardStore((s) => s.patchCard);
  const removeCard = useBoardStore((s) => s.removeCard);
  const persistLayout = useBoardStore((s) => s.persistLayout);
  const pins = useBoardStore((s) => s.pinsByCase[caseId]);
  const loading = useBoardStore((s) => s.loadingByCase[caseId] ?? false);
  const openEntity = useEntityStore((s) => s.open);
  const { checkLogs, busyId, check, resolve } = useHypotheses(caseId);

  const viewportRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState<View>({ x: 0, y: 0, k: 1 });
  const [panning, setPanning] = useState(false);
  const [linking, setLinking] = useState(false);
  const [linkSource, setLinkSource] = useState<string | null>(null);
  const [freshIds, setFreshIds] = useState<Set<string>>(() => new Set());
  const fittedRef = useRef(false);

  const persist = () => persistLayout(caseId);

  // ── lookups ────────────────────────────────────────────────────────────
  const hypById = useMemo(
    () => new Map(hypotheses.map((h) => [h.hypothesis_id, h])),
    [hypotheses],
  );

  const { suspectPinByRef, firPinByRef } = useMemo(() => {
    const suspect = new Map<string, PinnedItem>();
    const fir = new Map<string, PinnedItem>();
    (pins ?? []).forEach((p) => {
      const c = p.content as Record<string, any>;
      if (p.content_type === 'suspect') {
        const sid = String(c.id ?? c.label ?? c.name ?? '').trim();
        if (sid) suspect.set(sid, p);
      } else if (p.content_type === 'citation') {
        const f = String(c.fir_id ?? c.data?.crime_no ?? '').trim();
        if (f) fir.set(f, p);
      }
    });
    return { suspectPinByRef: suspect, firPinByRef: fir };
  }, [pins]);

  const refIds = useMemo(() => {
    const s = new Set<string>();
    cards.forEach((c) => {
      if (c.refId) s.add(c.refId);
    });
    return s;
  }, [cards]);

  // ── yarn edges ─────────────────────────────────────────────────────────
  const edges = useMemo<YarnEdge[]>(() => {
    const byId = new Map(cards.map((c) => [c.id, c]));
    const byRef = new Map<string, BoardCard>();
    cards.forEach((c) => {
      if (c.refId) byRef.set(c.refId, c);
    });
    const out: YarnEdge[] = [];
    const seen = new Set<string>();
    const add = (a: BoardCard, b: BoardCard, implicit: boolean) => {
      const key = [a.id, b.id].sort().join('~');
      if (seen.has(key)) return;
      seen.add(key);
      out.push({
        id: key,
        x1: a.x + a.w / 2,
        y1: a.y + a.h / 2,
        x2: b.x + b.w / 2,
        y2: b.y + b.h / 2,
        implicit,
        fresh: freshIds.has(key),
      });
    };
    cards.forEach((c) =>
      c.connections.forEach((other) => {
        const t = byId.get(other);
        if (t) add(c, t, false);
      }),
    );
    hypotheses.forEach((h) => {
      const src = byId.get(`hyp:${h.hypothesis_id}`);
      if (!src) return;
      h.linked_entity_ids.forEach((eid) => {
        const t = byRef.get(eid);
        if (t) add(src, t, true);
      });
    });
    return out;
  }, [cards, hypotheses, freshIds]);

  // ── wheel zoom (native, non-passive) ───────────────────────────────────
  useEffect(() => {
    const el = viewportRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      e.preventDefault();
      const rect = el.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      const my = e.clientY - rect.top;
      setView((v) => {
        const k = clamp(v.k * Math.exp(-e.deltaY * 0.0015), 0.4, 2);
        const bx = (mx - v.x) / v.k;
        const by = (my - v.y) / v.k;
        return { k, x: mx - bx * k, y: my - by * k };
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  // ── auto-fit once, after the server layout has loaded ─────────────────
  // (deriveBoardCards yields synth cards at scatter positions before the
  // layout doc arrives; fitting to those and then not re-fitting would leave
  // the real positions off-centre.)
  useEffect(() => {
    if (fittedRef.current || loading || cards.length === 0) return;
    fittedRef.current = true;
    const el = viewportRef.current;
    if (!el) return;
    const pad = 90;
    const minX = Math.min(...cards.map((c) => c.x)) - pad;
    const minY = Math.min(...cards.map((c) => c.y)) - pad;
    const maxX = Math.max(...cards.map((c) => c.x + c.w)) + pad;
    const maxY = Math.max(...cards.map((c) => c.y + c.h)) + pad;
    const vw = el.clientWidth;
    const vh = el.clientHeight;
    const k = clamp(Math.min(vw / (maxX - minX), vh / (maxY - minY)), 0.4, 1.5);
    setView({
      k,
      x: (vw - (maxX - minX) * k) / 2 - minX * k,
      y: (vh - (maxY - minY) * k) / 2 - minY * k,
    });
  }, [cards, loading]);

  // ── view helpers ───────────────────────────────────────────────────────
  const zoomAroundCentre = (factor: number) => {
    const el = viewportRef.current;
    if (!el) return;
    const mx = el.clientWidth / 2;
    const my = el.clientHeight / 2;
    setView((v) => {
      const k = clamp(v.k * factor, 0.4, 2);
      const bx = (mx - v.x) / v.k;
      const by = (my - v.y) / v.k;
      return { k, x: mx - bx * k, y: my - by * k };
    });
  };

  const fitAll = () => {
    const el = viewportRef.current;
    if (!el || cards.length === 0) {
      setView({ x: 0, y: 0, k: 1 });
      return;
    }
    const pad = 90;
    const minX = Math.min(...cards.map((c) => c.x)) - pad;
    const minY = Math.min(...cards.map((c) => c.y)) - pad;
    const maxX = Math.max(...cards.map((c) => c.x + c.w)) + pad;
    const maxY = Math.max(...cards.map((c) => c.y + c.h)) + pad;
    const vw = el.clientWidth;
    const vh = el.clientHeight;
    const k = clamp(Math.min(vw / (maxX - minX), vh / (maxY - minY)), 0.4, 1.5);
    setView({
      k,
      x: (vw - (maxX - minX) * k) / 2 - minX * k,
      y: (vh - (maxY - minY) * k) / 2 - minY * k,
    });
  };

  const boardCentre = () => {
    const el = viewportRef.current;
    const vw = el ? el.clientWidth / 2 : 320;
    const vh = el ? el.clientHeight / 2 : 220;
    return { x: (vw - view.x) / view.k, y: (vh - view.y) / view.k };
  };

  // ── mutations ──────────────────────────────────────────────────────────
  const markFresh = (key: string) => {
    setFreshIds((prev) => new Set(prev).add(key));
    window.setTimeout(() => {
      setFreshIds((prev) => {
        const n = new Set(prev);
        n.delete(key);
        return n;
      });
    }, 700);
  };

  // Toggle a cord between two cards: connected → cut it, otherwise draw it.
  const toggleLink = (aId: string, bId: string) => {
    const a = cards.find((c) => c.id === aId);
    const b = cards.find((c) => c.id === bId);
    if (!a || !b) return;
    upsertCard(caseId, a);
    upsertCard(caseId, b);
    const linked = a.connections.includes(bId) || b.connections.includes(aId);
    if (linked) {
      patchCard(caseId, aId, { connections: a.connections.filter((id) => id !== bId) });
      patchCard(caseId, bId, { connections: b.connections.filter((id) => id !== aId) });
    } else {
      patchCard(caseId, aId, { connections: [...a.connections, bId] });
      markFresh([aId, bId].sort().join('~'));
    }
    persist();
  };

  const addNote = () => {
    const { x, y } = boardCentre();
    upsertCard(caseId, {
      id: `note:${Date.now().toString(36)}`,
      kind: 'note',
      refId: null,
      x: x - 90,
      y: y - 60,
      w: 180,
      h: 120,
      color: 'var(--pin-gold)',
      rotation: jitter(),
      connections: [],
      text: '',
    });
    persist();
  };

  const addCardForEntity = (entityId: string) => {
    const id = `note:${entityId}`;
    if (cards.some((c) => c.id === id)) return;
    const { x, y } = boardCentre();
    upsertCard(caseId, {
      id,
      kind: 'note',
      refId: entityId,
      x: x - 90,
      y: y - 50,
      w: 180,
      h: 100,
      color: 'var(--pin-blue)',
      rotation: jitter(),
      connections: [],
      text: entityId,
    });
    persist();
  };

  const selectCard = (card: BoardCard) => {
    if (linking) {
      if (!linkSource) {
        setLinkSource(card.id);
        return;
      }
      if (linkSource !== card.id) toggleLink(linkSource, card.id);
      setLinkSource(null);
      return;
    }
    if (card.kind === 'suspect') {
      const p = suspectPinByRef.get(card.refId ?? '') ?? fallbackPin(card);
      const c = p.content as Record<string, any>;
      openEntity({
        type: 'person',
        id: card.refId ?? card.id,
        label: String(c.label ?? c.name ?? c.id ?? card.refId ?? 'Suspect'),
        data: c,
        linkedNodes: [],
        evidenceItems: [],
      });
    } else if (card.kind === 'fir') {
      const p = firPinByRef.get(card.refId ?? '') ?? fallbackPin(card);
      const c = p.content as Record<string, any>;
      openEntity({
        type: 'fir',
        id: card.refId ?? card.id,
        label: card.refId ?? 'Case File',
        data: (c.data as Record<string, any>) ?? c,
        evidenceItems: [c],
      });
    }
  };

  // ── panning the board ──────────────────────────────────────────────────
  const onViewportPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    if ((e.target as HTMLElement).closest('.board-card, .board-toolbar, .board-hint')) return;
    const startX = e.clientX;
    const startY = e.clientY;
    const ox = view.x;
    const oy = view.y;
    let moved = false;
    setPanning(true);
    const move = (ev: PointerEvent) => {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      if (!moved && Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      if (moved) setView((v) => ({ ...v, x: ox + dx, y: oy + dy }));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
      setPanning(false);
      if (!moved && linking) setLinkSource(null);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };

  const surfaceStyle: CSSProperties = {
    transform: `translate(${view.x}px, ${view.y}px) scale(${view.k})`,
  };

  return (
    <div className={`corkboard ${linking ? 'is-linking' : ''}`}>
      <BoardToolbar
        zoom={view.k}
        linking={linking}
        onAddNote={addNote}
        onToggleLink={() => {
          setLinking((v) => !v);
          setLinkSource(null);
        }}
        onZoomIn={() => zoomAroundCentre(1.2)}
        onZoomOut={() => zoomAroundCentre(1 / 1.2)}
        onFit={fitAll}
        onReset={() => setView({ x: 0, y: 0, k: 1 })}
      />

      <div
        ref={viewportRef}
        className={`corkboard-viewport ${panning ? 'is-panning' : ''}`}
        onPointerDown={onViewportPointerDown}
      >
        <div className="corkboard-surface" style={surfaceStyle}>
          <YarnLayer edges={edges} />
          {cards.map((card) => (
            <BoardCardFrame
              key={card.id}
              card={card}
              zoom={view.k}
              linking={linking}
              isLinkSource={linkSource === card.id}
              onDragMove={(x, y) => upsertCard(caseId, { ...card, x, y })}
              onDragEnd={persist}
              onSelect={() => selectCard(card)}
            >
              {card.kind === 'hypothesis' &&
                (() => {
                  const h = hypById.get(card.refId ?? '');
                  return h ? (
                    <HypothesisNoteCard
                      hypothesis={h}
                      checkLog={checkLogs[h.hypothesis_id]}
                      busy={busyId === h.hypothesis_id}
                      onCheck={check}
                      onResolve={resolve}
                      entityHasCard={(eid) => refIds.has(eid)}
                      onAddCardForEntity={addCardForEntity}
                    />
                  ) : (
                    <div className="free-note">Hypothesis unavailable</div>
                  );
                })()}
              {card.kind === 'suspect' && (
                <SuspectTile pin={suspectPinByRef.get(card.refId ?? '') ?? fallbackPin(card)} />
              )}
              {card.kind === 'fir' && (
                <FirCard pin={firPinByRef.get(card.refId ?? '') ?? fallbackPin(card)} />
              )}
              {card.kind === 'note' && (
                <FreeNoteCard
                  card={card}
                  onChangeText={(t) => {
                    patchCard(caseId, card.id, { text: t });
                    persist();
                  }}
                  onRemove={() => {
                    removeCard(caseId, card.id);
                    persist();
                  }}
                />
              )}
            </BoardCardFrame>
          ))}
        </div>
      </div>

      <div className="board-hint">
        {linking
          ? linkSource
            ? 'Pick a card to cord it to — or an already-corded one to cut it · click the board to cancel'
            : 'Link mode · click the first card'
          : 'Drag cards · scroll to zoom · drag the board to pan'}
      </div>
    </div>
  );
}
