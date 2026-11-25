# NEXORA — jury pitch

A seven-slide, three-minute React presentation for the hackathon jury, independent of the product (`apps/web`, the
API, the worker and PostgreSQL are untouched). It is a static site: no backend, no API calls, no analytics, no
third-party requests. Everything shown is public project information and **synthetic** data.

**Live:** https://pitch-production-1554324d.up.railway.app (redeploy after merging to publish this version)

## Run

```bash
cd apps/pitch && npm ci && npm run dev
```

Quality gates (also run by `.github/workflows/pitch.yml`):

```bash
npm run lint && npx tsc -b && npm test && npm run build && npm run test:e2e
```

Deep links: `#/6` (slide 6) or `#/6/2` (slide 6, state 2). Keys: `→ ↓ Space` next · `←` back ·
`Shift+→` next slide · `1–7` jump · `O` overview · `N` presenter notes + timer · `F` fullscreen · `R` restart ·
`?` help. Touch: swipe. `prefers-reduced-motion` is honoured.

## Story (180 s, 16 states)

One idea per slide, stated as its headline. Slides 2, 3 and 5 follow **one case** — collection funnel `··7530`
from the synthetic `demo-v1` dataset — from problem to method to the real product screen.

| # | Headline (the one idea) | States | Time | What the visual proves |
|---|---|---:|---:|---|
| 01 | Network investigation with evidence that can be checked | 1 | 10 s | Name, purpose, scope |
| 02 | A rule sees an account and cannot tell a scheme from a business | 2 | 25 s | Two identical account alerts → two networks of the same shape: a mule funnel and a merchant |
| 03 | Shape is only a reason to look; time and context decide | 3 | 35 s | Structure → chronology (81,9 %) → peers (not an outlier); priority, not probability |
| 04 | Every conclusion traces back to source transactions | 2 | 20 s | The six real pipeline stages, then three principles |
| 05 | The analyst gets a case with evidence, not an alert | 3 | 30 s | Real screens at native resolution: queue → investigation → decision and audit |
| 06 | A 4,5× shorter queue than the rules — at the cost of recall | 3 | 40 s | Gain (alerts, legitimate networks) → cost (recall −16,4 pp) → where the 19 misses are |
| 07 | First pilot step: offline replay on the bank's history | 2 | 20 s | Three-stage path, what the bank provides → QR and links |

## Design system

* Fixed 1920×1080 canvas scaled to fit (letterboxed, never clipped). Content grid: 120 px side margins, an 80 px
  hard safe area enforced by an e2e test on every element of every state; presentation chrome lives below it.
* All colours, sizes, spacing, radii and durations are tokens in `src/styles/tokens.css`. Flat dark surfaces; one
  brand accent (the product's violet); everything else is semantic: grey = monitoring rules, violet = NEXORA,
  amber = cost or caution, cyan/pink = money into/out of a central account (the product graph's hues).
* Type scale 168 / 56 / 44 / 34 / 32 / 28 / 24 / 22 px; headlines are one line; nothing is smaller than 22 canvas
  px (e2e-tested on all states). Onest + JetBrains Mono, self-hosted, the product's families.
* Motion is state-driven and explanatory (edges drawn in date order, bars grow, the product screen scrolls like
  an analyst would); back/forward/deep links are deterministic. No glow, glass or gradient text.

## Where the facts come from

| Slide | Source |
|---|---|
| 02, 03 | Case `··7530` copied from the product's investigation screen (`docs/design/screenshots/after/investigation-1440-dark.webp`) into `src/data/funnel.ts`. The merchant network on 02 is labelled as an illustration. |
| 04 | `docs/ARCHITECTURE.md`, root `README.md`, `CLAUDE.md` invariants. |
| 05 | Real screenshots of the production build (`public/shots/`), synthetic `demo-v1` data, shown at ≤ 1:1 (tested). |
| 06 | `src/data/bench-excerpt.json` — verbatim holdout excerpt of `benchmarks/results/bench-v1.json`; regenerate with `node scripts/extract-bench.mjs`. `bench.test.ts` fails if the excerpt drifts and pins every displayed number. |
| 07 | Pilot path from the spec's Q&A section; QR from `scripts/gen-qr.mjs` (a test checks it matches the link). |

## Content integrity (what is deliberately *not* claimed)

* **Percentages are computed from confusion counts.** Recall is 73/92 = 79,3 %; the artifact's pre-rounded
  `0.7935` would round again to 79,4 %, which earlier versions showed.
* **Metrics withdrawn after the PR #3 audit are not shown**: recall including "insufficient evidence"
  abstentions (label leak L-01) and P@5 (duplicate alerts, L-02). The slide says on screen that the holdout was
  read during development (L-03) and that the data is synthetic. An e2e test asserts these numbers never appear.
* The unmerged hypothesis engine and its sealed evaluation (PR #3) are not presented.
* No bank integration, savings, timelines, real-data accuracy or production readiness is claimed; an e2e test
  scans every state for such claims.

## Deploy (Railway, static service `pitch`)

The service is a `Dockerfile` (build with Vite, serve `dist/` with `server.mjs`: security headers + strict CSP, gzip,
immutable asset caching, `/healthz`, GET/HEAD only, no proxying). It shares nothing with the product services.

```bash
export RAILWAY_API_TOKEN=…   # account/workspace token
cd apps/pitch && railway link --project 7ebf5226-f80c-4098-9f5d-39417c03dae9 --environment production
railway up --service pitch --ci
node scripts/smoke.mjs https://pitch-production-1554324d.up.railway.app
```

The service needs `PORT=8080` and a healthcheck path of `/healthz`.
