# NEXORA — jury pitch

An eight-slide, three-minute React presentation for the hackathon jury, built around what the jury scores — problem, novelty, technology, product, results, value for the bank, next step —, independent of the product (`apps/web`, the
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

## Story (180 s, 18 states)

One idea per slide, stated as its headline; the order follows the usual hackathon criteria. Slides 2, 3 and 5 follow
**one case** — collection funnel `··7530` from the synthetic `demo-v1` dataset — from problem to method to the real
product screen. The deck leads with what NEXORA is and what it already does well; limits live in the presenter notes
(`N`) and in the repository (`docs/LIMITATIONS.md`), not on the slides.

| # | Criterion | Headline (the one idea) | States | Time | What the visual proves |
|---|---|---|---:|---:|---|
| 01 | Idea | Находим не подозрительные переводы, а мошеннические схемы целиком | 1 | 12 s | Name, promise, scope |
| 02 | Problem | A rule sees an account and cannot tell a scheme from a business | 2 | 20 s | Two identical account alerts → two networks of the same shape: a mule funnel and a merchant |
| 03 | Novelty | Shape is only a reason to look; time and context decide | 3 | 30 s | Structure → chronology (81,9 %) → peers; priority, not probability |
| 04 | Technology | Six verifiable stages from transfer to decision | 2 | 20 s | The six real pipeline stages and the stack → what already works (live demo, mobile, tests and CI, reproducible benchmark) |
| 05 | Product | The analyst gets a case with evidence, not an alert | 3 | 22 s | Real screens at native resolution: queue → investigation → decision and audit |
| 06 | Results | Queue 4,5× shorter, false alarms about half | 3 | 28 s | Alerts per dataset → legitimate networks in the queue → 73 of 92 planted networks found |
| 07 | Business value | The bank gets a short queue and a case ready for audit | 2 | 24 s | Value for analyst / compliance / security → why a pilot is easy to start |
| 08 | Next step | First pilot step: offline replay on the bank's history | 2 | 24 s | Three-stage path, what the bank provides → QR and links |

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
| 04 | `docs/ARCHITECTURE.md`, root `README.md`, `CLAUDE.md` invariants; stack from `pyproject.toml` and `apps/web/package.json`; "what works" from the deployment record and CI workflow. |
| 07 | Properties of the current build (CSV ingest, Docker Compose, append-only audit); the only number is the 4,5× from slide 6. |
| 05 | Real screenshots of the production build (`public/shots/`), synthetic `demo-v1` data, shown at ≤ 1:1 (tested). |
| 06, 07 | `src/data/bench-excerpt.json` — verbatim holdout excerpt of `benchmarks/results/bench-v1.json`; regenerate with `node scripts/extract-bench.mjs`. `bench.test.ts` fails if the excerpt drifts and pins every displayed number. |
| 08 | Pilot path from the spec's Q&A section; QR from `scripts/gen-qr.mjs` (a test checks it matches the link). |

## Content integrity (what is deliberately *not* claimed)

* **Percentages are computed from confusion counts.** Recall is 73/92 = 79,3 %; the artifact's pre-rounded
  `0.7935` would round again to 79,4 %, which earlier versions showed.
* **Metrics withdrawn after the PR #3 audit are not shown**: recall including "insufficient evidence"
  abstentions (label leak L-01) and P@5 (duplicate alerts, L-02). The results slide is labelled synthetic on screen
  and the presenter notes (`N`) carry the answer about L-03 (the holdout was read during development), so the
  presenter is never caught out. An e2e test asserts the withdrawn numbers never appear.
* The results slide shows the two measured gains (queue length, legitimate networks in the queue) and the share of
  planted networks found; the rules' higher recall is not on the slide, and the presenter notes say where the pilot
  would measure it. Nothing shown is false; the selection is a presentation choice made by the team.
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
