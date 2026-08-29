import type { CSSProperties } from 'react';

// Red-yarn layer. Each edge is a quadratic bezier with a downward-sagging
// control point so it hangs like real string between two pushpins. Explicit
// (user-drawn) links are solid; implicit links inferred from a hypothesis's
// linked_entity_ids are dashed and faint.

export interface YarnEdge {
  id: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  implicit?: boolean;
  fresh?: boolean;
}

const CANVAS = 12000;

export function YarnLayer({ edges }: { edges: YarnEdge[] }) {
  return (
    <svg className="corkboard-yarn" width={CANVAS} height={CANVAS} aria-hidden>
      {edges.map((e) => {
        const dx = e.x2 - e.x1;
        const dy = e.y2 - e.y1;
        const dist = Math.hypot(dx, dy);
        const mx = (e.x1 + e.x2) / 2;
        const my = (e.y1 + e.y2) / 2 + Math.min(90, dist * 0.22);
        const d = `M ${e.x1} ${e.y1} Q ${mx} ${my} ${e.x2} ${e.y2}`;
        const cls = ['', e.implicit ? 'is-implicit' : '', e.fresh && !e.implicit ? 'is-fresh' : '']
          .filter(Boolean)
          .join(' ');
        const style: CSSProperties | undefined =
          e.fresh && !e.implicit
            ? ({
                '--yarn-len': `${Math.round(dist * 1.4 + 120)}`,
                strokeDasharray: Math.round(dist * 1.4 + 120),
              } as CSSProperties)
            : undefined;
        return <path key={e.id} className={cls || undefined} d={d} style={style} />;
      })}
    </svg>
  );
}
