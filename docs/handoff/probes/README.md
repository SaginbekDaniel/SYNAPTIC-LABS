# Measurement probes

Throw-away, reproducible measurements behind the performance findings in
[`../MASTER_HANDOFF.md`](../MASTER_HANDOFF.md) (§16). They are **not** part of the product, the test
suite or CI, and their data is synthetic and unrepresentative — they show how cost grows with input
size, not how real banking data behaves. Re-run them before and after a performance change and quote
the literal output.

| Probe | Command (repository root) | Needs |
|---|---|---|
| Analysis pipeline, time and peak RSS at N transfers | `uv run python docs/handoff/probes/scale_pipeline.py 200000` | nothing |
| Graph read model, hub with many counterparties | `uv run python docs/handoff/probes/scale_graph.py 20000 160000` | a **development** PostgreSQL (`NEXORA_PROBE_DATABASE_URL`, default the `nexora` dev database, migrated); seeds and deletes its own dataset |
| Cytoscape `cose` layout time (main thread in the app) | `node docs/handoff/probes/cose_layout.mjs` | `cd apps/web && npm ci` |
| Run the Playwright suite against the **production bundle** with the exact gateway headers | see below (`gateway_sim.mjs`) | `cd apps/web && npx vite build` |
| Mechanical consistency check of the handoff documents (paths, links, branches, SHAs, commands, task graph) | `python3 docs/handoff/probes/check_handoff_docs.py` | git, python3 |

Observed 2026-11-22 (single-core container; see MASTER_HANDOFF §16 for interpretation):

```
scale_pipeline  N=2000 0.1 s / 37 MiB · 10000 0.6 s / 51 · 50000 5.9 s / 120 · 100000 10.4 s / 208 · 200000 22.5 s / 381
scale_graph     hub 20000 peers, 199996 rows: local depth1 215 ms · depth2 (200 nodes) 640 ms · depth2 (300 nodes) 437 ms;
                one hub expansion returns 40000 aggregate rows to Python, 398 edges kept
cose_layout     50 nodes 109 ms · 100: 355 ms · 200: 1150 ms · 300: 2791 ms
```

Re-measured 2026-11-22 after B-020 (Chromium, synthetic graph of n accounts / 1.5 n transfers served in place of the real
graph response, `PerformanceObserver` long tasks; scratch spec, deleted — the committed E2E in
`apps/web/e2e/graph-workspace.spec.ts` asserts the 300-account case):

```
before (synchronous cose on the main thread, dev server)  100: one 750 ms long task · 200: 2462 ms · 300: canvas not shown within 5 s
after  (worker, production bundle)  layout in the worker 100: 374 ms · 200: 1618 ms · 300: 2645 ms · 400: 3879 ms
                                    long tasks while the worker computes: none at any size
                                    largest main-thread tasks: setup 67–229 ms (before), drawing the result 64–199 ms (after)
```

## Production-bundle run (what `gateway_sim.mjs` is for)

Not the real Nginx (no rate limits, token or gzip; CI exercises the real image) — it serves `dist/` with exactly the headers `docker/csp.mjs` generates,
so CSP problems in the built bundle show up locally. From `apps/web`:

```bash
npx vite build && node docker/csp.mjs dist/index.html > /tmp/security-headers.conf
cat > playwright.prodcsp.tmp.config.ts <<'CFG'
import base from "./playwright.config";
const cfg = { ...base, webServer: [ (base.webServer as any[])[0], { command: "node ../../docs/handoff/probes/gateway_sim.mjs dist /tmp/security-headers.conf 5180 8100", url: "http://127.0.0.1:5180", reuseExistingServer: false, timeout: 30000 } ] };
export default cfg;
CFG
npx playwright test -c playwright.prodcsp.tmp.config.ts --trace off; rm playwright.prodcsp.tmp.config.ts
```

Observed 2026-11-22: 34 passed (4 gestures, 5 graph-workspace). Delete the temporary config afterwards; never commit it.
