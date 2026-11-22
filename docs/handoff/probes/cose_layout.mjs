// Probe: wall-clock of Cytoscape's cose layout at the options GraphCanvas.tsx uses, headless.
// In the app this runs synchronously on the main thread. Usage: node docs/handoff/probes/cose_layout.mjs
import { createRequire } from "node:module";
const require = createRequire(new URL("../../../apps/web/package.json", import.meta.url));
const cytoscape = require("cytoscape");
function rngf(seed) { let s = seed >>> 0; return () => (s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32; }
for (const n of [50, 100, 200, 300]) {
  const r = rngf(n), els = [];
  for (let i = 0; i < n; i++) els.push({ data: { id: `n${i}` }, position: { x: r() * 800, y: r() * 600 } });
  for (let i = 1; i < n; i++) els.push({ data: { id: `e${i}`, source: `n${i}`, target: `n${Math.floor(r() * i)}` } });
  for (let i = 0; i < n / 2; i++) els.push({ data: { id: `x${i}`, source: `n${Math.floor(r() * n)}`, target: `n${Math.floor(r() * n)}` } });
  const cy = cytoscape({ headless: true, elements: els.filter((e) => !e.data.source || e.data.source !== e.data.target) });
  const t = performance.now();
  cy.layout({ name: "cose", randomize: false, animate: false, nodeRepulsion: () => 9000, idealEdgeLength: () => 95, nodeOverlap: 12, numIter: 1000, padding: 36 }).run();
  console.log(`nodes=${n} edges=${cy.edges().length} cose layout ${(performance.now() - t).toFixed(0)} ms`);
}
process.exit(0);
