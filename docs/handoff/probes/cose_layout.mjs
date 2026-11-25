// Probe: wall-clock of Cytoscape's cose layout at the options the graph workspace uses, headless.
// Since B-020 the app runs it in a worker (apps/web/src/components/graph/coseLayout.ts); this probe shows
// what that worker (or the main-thread fallback) spends. Usage: node docs/handoff/probes/cose_layout.mjs
//
// "app" = how coseLayout.ts runs it: explicit preset layout (keeps the seed positions), node sizes from
// the stylesheet (21 px = 18 + border 3). "pre-B-020 probe" = how this probe ran before 2026-11-23:
// no layout option, so the constructor's null layout put every node at (0, 0), and no style, so every
// node measured 1 px with NaN padding — cose then started from one point and drew Math.random().
import { createRequire } from "node:module";
const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const cytoscape = require("cytoscape");
const OPTIONS = { name: "cose", randomize: false, animate: false, fit: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 95, nodeOverlap: 12, numIter: 1000, padding: 36 };
function rngf(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32; }
function graph(n) {
  const r = rngf(n), els = [];
  for (let i = 0; i < n; i++) els.push({ data: { id: `n${i}`, size: 21 }, position: { x: r() * 800, y: r() * 600 } });
  for (let i = 1; i < n; i++) els.push({ data: { id: `e${i}`, source: `n${i}`, target: `n${Math.floor(r() * i)}` } });
  for (let i = 0; i < n / 2; i++) els.push({ data: { id: `x${i}`, source: `n${Math.floor(r() * n)}`, target: `n${Math.floor(r() * n)}` } });
  return els.filter((e) => !e.data.source || e.data.source !== e.data.target);
}
const variants = {
  app: (els) => cytoscape({ headless: true, styleEnabled: true, layout: { name: "preset" }, style: [{ selector: "node", style: { width: "data(size)", height: "data(size)", "border-width": 0 } }], elements: els }),
  "pre-B-020 probe": (els) => cytoscape({ headless: true, elements: els }),
};
for (const [name, make] of Object.entries(variants)) {
  for (const n of [50, 100, 200, 300, 400]) {
    const cy = make(graph(n));
    const random = Math.random;
    let draws = 0;
    Math.random = () => (draws++, random());
    const t = performance.now();
    cy.layout(OPTIONS).run();
    const ms = performance.now() - t;
    Math.random = random;
    console.log(`${name.padEnd(16)} nodes=${n} edges=${cy.edges().length} cose ${ms.toFixed(0)} ms, Math.random draws ${draws}`);
    cy.destroy();
  }
}
process.exit(0);
