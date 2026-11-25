import { m } from "motion/react";
import type { GEdge, GNode } from "../data/funnel";
import { EASE } from "./primitives";

const R = { in: 13, out: 13, hub: 22, plain: 11 } as const;
const COLOR = { in: "var(--in)", out: "var(--out)", hub: "var(--accent)", plain: "var(--node)" } as const;

interface Props {
  nodes: GNode[];
  edges: GEdge[];
  /** which edges are drawn (others stay hidden) */
  showEdge?: (e: GEdge, i: number) => boolean;
  /** which nodes are drawn at full strength (others are dim placeholders) */
  showNode?: (n: GNode) => boolean;
  /** label on each visible edge */
  edgeLabel?: (e: GEdge) => string;
  /** monochrome rendering (the "rules" view); colours return when false */
  mono?: boolean;
  /** stagger edges by their day so the drawing reads as a timeline */
  byDay?: boolean;
  title: string;
  width?: number;
  height?: number;
}

/**
 * Small directed transfer graph. Edges are drawn as straight lines that stop at the node rim with an arrowhead;
 * labels sit on a background stroke so they never collide with lines. Purely presentational.
 */
export function Graph({ nodes, edges, showEdge = () => true, showNode = () => true, edgeLabel, mono, byDay, title, width = 760, height = 520 }: Props) {
  const at = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const firstDay = Math.min(...edges.map((e) => e.day));
  return (
    <svg className="graph" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
      <defs>
        {(["in", "out", "plain"] as const).map((k) => (
          <marker key={k} id={`ah-${k}`} viewBox="0 0 10 10" refX="5" refY="5" markerWidth="5" markerHeight="5" orient="auto">
            <path d="M0 0L10 5L0 10z" fill={k === "plain" ? "var(--text-3)" : COLOR[k]} />
          </marker>
        ))}
      </defs>
      {edges.map((e, i) => {
        const a = at[e.from], b = at[e.to];
        const dx = b.x - a.x, dy = b.y - a.y, len = Math.hypot(dx, dy);
        const ux = dx / len, uy = dy / len;
        const x1 = a.x + ux * (R[a.kind] + 6), y1 = a.y + uy * (R[a.kind] + 6);
        const x2 = b.x - ux * (R[b.kind] + 6), y2 = b.y - uy * (R[b.kind] + 6);
        const tone = mono ? "plain" : b.kind === "hub" ? "in" : "out";
        const on = showEdge(e, i);
        const delay = byDay ? (e.day - firstDay) * 0.22 : i * 0.05;
        const label = on && edgeLabel ? edgeLabel(e) : "";
        const mx = (x1 + x2) / 2, my = (y1 + y2) / 2;
        // labels sit away from the mid-edge arrow: near the source for inflows, near the target for outflows
        const t = b.kind === "hub" ? 0.26 : 0.74;
        const lx = x1 + (x2 - x1) * t, ly = y1 + (y2 - y1) * t;
        return (
          <g key={`${e.from}-${e.to}`}>
            <m.path
              d={`M${x1} ${y1}L${mx} ${my}L${x2} ${y2}`} fill="none"
              stroke={tone === "plain" ? "var(--text-3)" : COLOR[tone]} strokeWidth={3} strokeLinecap="round"
              markerMid={`url(#ah-${tone})`}
              initial={false}
              animate={{ pathLength: on ? 1 : 0, opacity: on ? 0.9 : 0 }}
              transition={{ duration: 0.6, delay: on ? delay : 0, ease: EASE }}
            />
            {label && (
              <m.text
                className="g-elabel" x={lx} y={ly - 14} textAnchor="middle"
                initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: delay + 0.35, duration: 0.4 }}
              >{label}</m.text>
            )}
          </g>
        );
      })}
      {nodes.map((n) => {
        const on = showNode(n);
        const fill = mono ? (n.kind === "hub" ? "var(--text-2)" : "var(--node)") : COLOR[n.kind];
        const left = n.kind === "in", right = n.kind === "out";
        return (
          <g key={n.id}>
            <m.circle cx={n.x} cy={n.y} r={R[n.kind]} initial={false} animate={{ opacity: on ? 1 : 0.18, fill }} transition={{ duration: 0.5 }} />
            <m.text
              className="g-nlabel mono" initial={false} animate={{ opacity: on ? 1 : 0 }} transition={{ duration: 0.4 }}
              x={left ? n.x - R[n.kind] - 14 : right ? n.x + R[n.kind] + 14 : n.x}
              y={left || right ? n.y + 8 : n.y + R[n.kind] + 34}
              textAnchor={left ? "end" : right ? "start" : "middle"}
            >{n.label}</m.text>
          </g>
        );
      })}
    </svg>
  );
}
