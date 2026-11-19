# NEXORA AI — interactive pitch

A six-slide, ~3 minute React presentation for the hackathon, independent of the product (`apps/web`, the API, the
worker and PostgreSQL are untouched). It is a static site: no backend, no API calls, no analytics, no third-party
requests. Everything shown is public project information and **synthetic** data.

**Live:** https://pitch-production-1554324d.up.railway.app

## Run

```bash
cd apps/pitch && npm ci && npm run dev
```

Quality gates (also run by `.github/workflows/pitch.yml`):

```bash
npm run lint && npx tsc -b && npm test && npm run build && npm run test:e2e
```

Deep links: `#/3` (slide 3) or `#/3/7` (slide 3, reveal state 7). Keys: `→ ↓ Space` next · `←` back ·
`Shift+→` next slide · `1–6` jump · `O` overview · `N` presenter notes + timer · `F` fullscreen · `R` restart · `?` help.
Touch: swipe. `prefers-reduced-motion` is honoured.

## Design system

* Fixed 1920×1080 canvas scaled to fit (letterboxed, never clipped) with an **80 px safe area on every side**.
  Presentation chrome lives in the bottom margin and never covers content. An e2e test checks every element of
  every one of the 28 reveal states against the safe area.
* All colours, sizes, radii and durations are tokens in `src/styles/tokens.css`. No text is smaller than 22 canvas px
  (also enforced by a test).
* Onest + JetBrains Mono, self-hosted (`@fontsource-variable`), the same families as the product.
* Motion is state-driven: a reveal state fully determines the picture; animation only interpolates between states,
  so back/forward/deep links are deterministic.

## Where the facts come from

| Slide | Source |
|---|---|
| 02, 03 | `README.md`, `docs/ARCHITECTURE.md`, `docs/architecture/HYPOTHESIS_ENGINE.md` (PR #3), `apps/web/src/lib/i18n.ts` |
| 04 | Real product screenshots (`docs/design/screenshots/after/*`, `docs/assets/screenshots/*` from PR #4), cropped. Synthetic `demo-v1` data. |
| 05 | `src/data/sealed-excerpt.json` — verbatim excerpt of `benchmarks/results/sealed-evaluation.json` (PR #3, commit `eece2de`/`686f4ce`). `src/data/results.ts` derives every displayed number from it; `results.test.ts` pins them. |

## Content integrity (what is deliberately *not* claimed)

* **PR #3 (hypothesis engine v3, `risk-policy-v3`, sealed-v1) is not merged into `main`.** Slides 2, 3 and 5 label it
  "PR №3 · не в main". The 50.7 → 15.9 % etc. compare `v2` (in main) with the unmerged candidate.
* The animations on slides 1–3 are **illustrations**, not product output; slide 1 says so on screen. Slide 3's
  hypothesis scoring reproduces the documented rules (`src/data/hypotheses.ts`, tested) on illustrative observations and
  never produces a probability.
* No bank integration, no real-data accuracy, no production-readiness claim, no LLM in detection. Slide 5 carries the
  mandatory synthetic-benchmark disclaimer.
* There is no public deployment of the product itself; slide 4 links to the repository only.

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
