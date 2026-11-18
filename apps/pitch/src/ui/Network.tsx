import { useId } from "react";
import { m, useReducedMotion } from "motion/react";

export type Tone = "neutral" | "dim" | "source" | "hub" | "sink" | "risk" | "legit" | "warn";

export interface NodeSpec {
  id: string;
  x: number;
  y: number;
  tone?: Tone;
  r?: number;
  label?: string;
  hidden?: boolean;
  pulse?: boolean;
}
export interface EdgeSpec {
  id: string;
  from: string;
  to: string;
  tone?: Tone;
  flow?: boolean;
  hidden?: boolean;
  width?: number;
  label?: string;
  /** makes the edge keyboard- and pointer-selectable */
  onSelect?: () => void;
  ariaLabel?: string;
  /** CSS hook, e.g. the sequential scan highlight */
  className?: string;
  scanDelay?: number;
}

interface Props {
  width: number;
  height: number;
  nodes: NodeSpec[];
  edges: EdgeSpec[];
  duration?: number;
  label: string;
  className?: string;
}

const TONES: Tone[] = ["neutral", "dim", "source", "hub", "sink", "risk", "legit", "warn"];

/**
 * Animated directed graph. Geometry is driven by props, so every state is deterministic:
 * the same props always produce the same picture; motion only interpolates between states.
 */
export function Network({ width, height, nodes, edges, duration = 0.9, label, className }: Props) {
  const uid = useId().replace(/:/g, "");
  const reduced = useReducedMotion();
  const tr = reduced ? { duration: 0 } : { duration, ease: [0.22, 1, 0.36, 1] as const };
  const byId = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg className={`net ${className ?? ""}`} viewBox={`0 0 ${width} ${height}`} width={width} height={height} role="img" aria-label={label}>
      <defs>
        {TONES.map((t) => (
          <marker key={t} id={`${uid}-${t}`} viewBox="0 0 10 10" refX="8" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M0 0 L10 5 L0 10 z" className={`tone-${t}`} style={{ fill: "var(--tone)" }} />
          </marker>
        ))}
      </defs>

      {edges.map((e) => {
        const a = byId.get(e.from);
        const b = byId.get(e.to);
        if (!a || !b) return null;
        const dx = b.x - a.x;
        const dy = b.y - a.y;
        const len = Math.hypot(dx, dy);
        const ux = len > 1 ? dx / len : 0;
        const uy = len > 1 ? dy / len : 0;
        const ra = (a.r ?? 12) + 4;
        const rb = (b.r ?? 12) + 10;
        const x1 = a.x + ux * ra;
        const y1 = a.y + uy * ra;
        const x2 = b.x - ux * rb;
        const y2 = b.y - uy * rb;
        const tone = e.tone ?? "neutral";
        const opacity = e.hidden ? 0 : 1;
        return (
          <g key={e.id}>
            <m.line
              className={`edge tone-${tone} ${e.flow && !e.hidden ? "flow" : ""} ${e.className ?? ""}`}
              style={e.scanDelay !== undefined ? ({ "--d": `${e.scanDelay}s` } as React.CSSProperties) : undefined}
              initial={{ x1, y1, x2, y2, opacity: 0 }}
              animate={{ x1, y1, x2, y2, opacity, strokeWidth: e.width ?? 3 }}
              transition={tr}
              markerEnd={`url(#${uid}-${tone})`}
            />
            {e.label && !e.hidden && (
              <m.text
                className="elabel"
                initial={{ x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 14, opacity: 0 }}
                animate={{ x: (x1 + x2) / 2, y: (y1 + y2) / 2 - 14, opacity: 1 }}
                transition={tr}
              >
                {e.label}
              </m.text>
            )}
            {e.onSelect && !e.hidden && (
              <line
                className="hit"
                x1={x1} y1={y1} x2={x2} y2={y2}
                tabIndex={0}
                role="button"
                aria-label={e.ariaLabel ?? "Перевод"}
                onClick={e.onSelect}
                onKeyDown={(ev) => {
                  if (ev.key === "Enter" || ev.key === " ") {
                    ev.preventDefault();
                    e.onSelect?.();
                  }
                }}
              />
            )}
          </g>
        );
      })}

      {nodes.map((n) => {
        const r = n.r ?? 12;
        const op = n.hidden ? 0 : 1;
        return (
          <g key={n.id} className={`tone-${n.tone ?? "neutral"}`}>
            {n.pulse && !n.hidden && <m.circle className="halo pulse" initial={false} animate={{ cx: n.x, cy: n.y, r: r * 2.2 }} transition={tr} />}
            <m.circle
              className="node"
              initial={{ cx: n.x, cy: n.y, r: 0, opacity: 0 }}
              animate={{ cx: n.x, cy: n.y, r, opacity: op }}
              transition={tr}
            />
            {n.label && !n.hidden && (
              <m.text
                className="nlabel"
                initial={{ x: n.x, y: n.y + r + 28, opacity: 0 }}
                animate={{ x: n.x, y: n.y + r + 28, opacity: 1 }}
                transition={tr}
              >
                {n.label}
              </m.text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
