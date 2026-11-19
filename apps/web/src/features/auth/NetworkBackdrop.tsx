import { useId } from "react";

/**
 * Decorative financial-network illustration for the sign-in screen: funds enter (cyan), converge on
 * a hub (violet) and leave (pink), over a faint background mesh. Abstract and fixed — no labels,
 * amounts or identifiers, nothing resembling a customer record. Hidden from assistive technology.
 * All motion is CSS and is switched off under prefers-reduced-motion (see styles/auth.css).
 */
type Role = "hub" | "entry" | "relay" | "exit" | "far" | "mesh";

const NODES: Record<string, { x: number; y: number; role: Role }> = {
  hub: { x: 330, y: 262, role: "hub" },
  e1: { x: 138, y: 126, role: "entry" },
  e2: { x: 92, y: 272, role: "entry" },
  e3: { x: 160, y: 404, role: "entry" },
  m1: { x: 232, y: 196, role: "relay" },
  m2: { x: 236, y: 336, role: "relay" },
  x1: { x: 456, y: 150, role: "exit" },
  x2: { x: 508, y: 284, role: "exit" },
  x3: { x: 446, y: 414, role: "exit" },
  f1: { x: 600, y: 196, role: "far" },
  f2: { x: 604, y: 372, role: "far" },
  b1: { x: 46, y: 58, role: "mesh" },
  b2: { x: 300, y: 64, role: "mesh" },
  b3: { x: 430, y: 34, role: "mesh" },
  b4: { x: 620, y: 70, role: "mesh" },
  b5: { x: 36, y: 452, role: "mesh" },
  b6: { x: 312, y: 484, role: "mesh" },
  b7: { x: 580, y: 492, role: "mesh" },
  b8: { x: 210, y: 40, role: "mesh" },
  b9: { x: 372, y: 372, role: "mesh" },
};

/** Transaction paths: animated flow, in order of the scheme (entry → relay → hub → exit → onward). */
const FLOWS: [string, string][] = [
  ["e1", "m1"], ["e2", "m1"], ["e2", "m2"], ["e3", "m2"],
  ["m1", "hub"], ["m2", "hub"],
  ["hub", "x1"], ["hub", "x2"], ["hub", "x3"],
  ["x1", "f1"], ["x2", "f1"], ["x2", "f2"], ["x3", "f2"],
];

/** Unrelated background connections: static and faint. */
const MESH: [string, string][] = [
  ["b1", "e1"], ["b1", "b8"], ["b8", "b2"], ["b8", "m1"], ["b2", "b3"], ["b3", "x1"], ["b3", "b4"], ["b4", "f1"],
  ["b5", "e3"], ["b5", "e2"], ["b6", "m2"], ["b6", "b9"], ["b9", "x3"], ["b9", "hub"], ["b6", "b7"], ["b7", "f2"],
  ["b2", "hub"], ["e1", "e2"],
];

function curve(a: string, b: string, i: number, strength: number): string {
  const p = NODES[a]!;
  const q = NODES[b]!;
  const mx = (p.x + q.x) / 2;
  const my = (p.y + q.y) / 2;
  const dx = q.x - p.x;
  const dy = q.y - p.y;
  const bend = i % 2 === 0 ? strength : -strength; // alternate sides so parallel paths don't overlap
  return `M${p.x} ${p.y}Q${(mx - dy * bend).toFixed(1)} ${(my + dx * bend).toFixed(1)} ${q.x} ${q.y}`;
}

const RADIUS: Record<Role, number> = { hub: 9, entry: 6, relay: 5, exit: 6, far: 5, mesh: 3 };
const PULSING = new Set(["hub", "e2", "x2"]);

export function NetworkBackdrop() {
  const id = useId().replace(/:/g, "");
  return (
    <svg className="netviz" viewBox="0 0 660 520" preserveAspectRatio="xMidYMid meet" aria-hidden="true" focusable="false">
      <defs>
        <radialGradient id={`${id}-glow`}>
          <stop offset="0" style={{ stopColor: "var(--accent)", stopOpacity: 0.32 }} />
          <stop offset="1" style={{ stopColor: "var(--accent)", stopOpacity: 0 }} />
        </radialGradient>
      </defs>
      <circle className="netviz__glow" cx={NODES.hub!.x} cy={NODES.hub!.y} r="170" fill={`url(#${id}-glow)`} />

      <g className="netviz__mesh">
        {MESH.map(([a, b], i) => (
          <path key={`${a}-${b}`} d={curve(a, b, i, 0.04)} />
        ))}
      </g>

      <g className="netviz__paths">
        {FLOWS.map(([a, b], i) => (
          <path key={`${a}-${b}`} d={curve(a, b, i, 0.1)} data-from={NODES[a]!.role} />
        ))}
      </g>
      {/* A short dash travelling once along each normalised path reads as a moving transfer. */}
      <g className="netviz__packets">
        {FLOWS.map(([a, b], i) => (
          <path key={`${a}-${b}`} d={curve(a, b, i, 0.1)} pathLength={100} data-from={NODES[a]!.role} style={{ animationDelay: `${(i * 0.37) % 3.2}s` }} />
        ))}
      </g>

      <g className="netviz__nodes">
        {Object.entries(NODES).map(([key, n]) => (
          <g key={key} data-role={n.role}>
            {PULSING.has(key) && <circle className="netviz__pulse" cx={n.x} cy={n.y} r={RADIUS[n.role] + 2} style={{ animationDelay: `${key === "hub" ? 0 : key === "e2" ? 1.1 : 2.2}s` }} />}
            <circle className="netviz__node" cx={n.x} cy={n.y} r={RADIUS[n.role]} />
          </g>
        ))}
      </g>
    </svg>
  );
}
