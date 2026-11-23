/**
 * The graph workspace's force layout as a pure function, so it can run in a worker (layoutWorker.ts)
 * instead of blocking the main thread for seconds (H-04: 750 ms at 100 nodes, 2.5 s at 200 in Chromium).
 *
 * Same algorithm and options the canvas used to run in place (Cytoscape `cose`, seeded positions,
 * `randomize: false`), with two inputs made explicit instead of read from the page:
 *  - node sizes: measured from the live stylesheet on the main thread and passed in;
 *  - the gravity centre: cose pulls towards the centre of its container, which made the picture depend on
 *    the viewport size (and put the centre at the origin for a not-yet-laid-out container). A headless
 *    instance has a fixed 1×1 "container", so the centre is fixed near the origin, where the seed positions
 *    are centred (graphModel.seedPosition). Same input → same positions, on every screen size.
 * The canvas then fits the result to the viewport, as before.
 */
import cytoscape from "cytoscape";

/** Bump when the options or the inputs change: it is part of the cache key. */
export const COSE_LAYOUT_VERSION = "cose-v2";

export interface LayoutNodeInput {
  id: string;
  x: number;
  y: number;
  /** Layout dimensions of the drawn node (Cytoscape `layoutDimensions`), in model pixels. */
  w: number;
  h: number;
}

export interface LayoutInput {
  /** Order matters to cose; callers pass the canvas element order. */
  nodes: LayoutNodeInput[];
  edges: { source: string; target: string }[];
}

/** x, y per node, in the order of `input.nodes`. */
export type LayoutPositions = Float64Array;

export const COSE_OPTIONS = {
  name: "cose",
  // Seeded positions (graphModel.seedPosition) and no coincident nodes: cose never consults Math.random.
  randomize: false,
  animate: false,
  fit: false,
  nodeRepulsion: () => 9000,
  idealEdgeLength: () => 95,
  nodeOverlap: 12,
  numIter: 1000,
  padding: 36,
} as const;

export function computeCoseLayout(input: LayoutInput): LayoutPositions {
  const ids = new Set(input.nodes.map((n) => n.id));
  const cy = cytoscape({
    headless: true,
    styleEnabled: true,
    elements: [
      ...input.nodes.map((n) => ({ data: { id: n.id, w: n.w, h: n.h }, position: { x: n.x, y: n.y } })),
      ...input.edges
        .filter((e) => ids.has(e.source) && ids.has(e.target))
        .map((e, i) => ({ data: { id: `e${i}`, source: e.source, target: e.target } })),
    ],
    style: [{ selector: "node", style: { width: "data(w)", height: "data(h)", "border-width": 0, padding: "0" } }],
    // Keep the seeds: a headless instance otherwise runs the "null" layout, which moves every node to (0, 0);
    // coincident nodes make cose fall back to Math.random and the picture stops being reproducible.
    layout: { name: "preset" },
  });
  cy.layout(COSE_OPTIONS as unknown as cytoscape.LayoutOptions).run();
  const out = new Float64Array(input.nodes.length * 2);
  input.nodes.forEach((n, i) => {
    const p = cy.getElementById(n.id).position();
    out[2 * i] = p.x;
    out[2 * i + 1] = p.y;
  });
  cy.destroy();
  return out;
}

/**
 * A compact, order-sensitive fingerprint of everything that determines the result. Every field is
 * length-prefixed, so no account id (an opaque string) can make two different inputs serialise alike;
 * two independent 32-bit FNV-style lanes make an accidental hash collision negligible for a cache.
 */
export function layoutKey(input: LayoutInput): string {
  let a = 0x811c9dc5;
  let b = 0x9747b28c;
  const field = (value: string | number) => {
    const s = String(value);
    const text = `${s.length}:${s}`;
    for (let i = 0; i < text.length; i++) {
      const c = text.charCodeAt(i);
      a = Math.imul(a ^ c, 0x01000193);
      b = Math.imul(b ^ c, 0x5bd1e995);
      b ^= b >>> 13;
    }
  };
  field(COSE_LAYOUT_VERSION);
  field(input.nodes.length);
  for (const n of input.nodes) [n.id, n.x, n.y, n.w, n.h].forEach(field);
  field(input.edges.length);
  for (const e of input.edges) [e.source, e.target].forEach(field);
  return `${input.nodes.length}.${input.edges.length}.${(a >>> 0).toString(36)}.${(b >>> 0).toString(36)}`;
}
