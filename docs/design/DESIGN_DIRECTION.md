# NEXORA Dark Intelligence — design direction

## What was wrong before

Screenshots: `screenshots/before/`.

* **No user journey.** Navigation mirrored backend modules (Алерты, Кейсы, Граф связей, Fraud Lab,
  Оценка качества) as six peers. The overview opened with snapshot hashes and gave no next step.
* **Investigation was one long scroll.** Hypothesis, a small graph, temporal facts, peer facts and the
  evidence table stacked vertically; the decision lived in a side column far from the evidence it
  depends on; clicking the graph did nothing useful.
* **Raw identifiers as titles** ("Воронка сбора средств · 6300477387530").
* **Phones** got a clipped horizontal strip of six nav links.
* **Charts**: none — every distribution was a list of badges and numbers.

## Directions considered

| | A. Analyst console (chosen) | B. Editorial report | C. Command-room HUD |
|---|---|---|---|
| Idea | The reference's near-black canvas, pill navigation and calm panels; one expressive surface — the graph stage | Light, typographic, long-form "case file" with hairline rules | Dense multi-panel wall, neon accents, live-feel tickers |
| FinTech credibility | High | High | Low — implies real-time monitoring the product does not do |
| Usability for triage | High (task-ordered, split views) | Medium (good for reading, slow for queue work) | Low (noise) |
| Accessibility | Good with controlled contrast | Best | Poor (neon on black) |
| Fit to the brief | Matches the reference and "dark as the main experience" | Contradicts the dark brief | Contradicts "avoid neon overload" |

A was chosen; B informed the light theme (white panels, restrained borders); C was rejected.

## Token plan

| Name | Dark | Light | Role |
|---|---|---|---|
| Canvas | `#08090D` | `#F3F3F7` | app background |
| Panel | `#10111A` | `#FFFFFF` | top-level surfaces |
| Raised | `#171925` / `#20223A` | `#F6F6FA` / `#EBE9F6` | inputs, hover, active pills |
| Violet | `#A58BF5` (text) · `#7C5CE6` (fill) | `#5B3FD0` · `#6447D8` | primary action, subject node, primary series |
| Cyan | `#62D3DB` | `#0B8790` | inflow / secondary series |
| Pink | `#DA7FD0` | `#A8418F` | outflow / legitimate-family series |

Risk bands have their own hue **and icon shape** (octagon, triangle, diamond, dashed circle) so
meaning never depends on colour. Evidence status uses check / dash / cross / dotted circle.
All values live in `apps/web/src/styles/tokens.css`; feature CSS references tokens only.

* **Type**: Onest (variable, self-hosted via `@fontsource-variable`, OFL) for all text with tabular
  figures; JetBrains Mono only for opaque identifiers. Scale 11/12/13/14/16/20/26/34 px.
* **Radii hierarchy**: 22 px panels → 16 nested → 12 buttons/tiles → 8 inputs → pill for navigation
  and filters. Not one radius everywhere.
* **Elevation**: dark relies on surface steps and 1 px lines; shadows only on floating layers
  (tooltips, graph controls, sheet). Light adds a hairline panel shadow.
* **Motion**: 120/200/320 ms, one ease-out curve; all zeroed under `prefers-reduced-motion`.
  Motion only answers actions (preview slide-in, context-panel fade, confirmation).
* **Breakpoints**: 600 · 768 · 1100 · 1280 (documented in `tokens.css`).

## Information architecture

```
Primary (task order)            Tools (secondary)
Обзор        understand         Лаборатория   synthetic scenarios
Проверки     prioritise         Граф связей   free account exploration
Расследования decide/review
Аналитика    evaluate  ─┬─ Набор данных (distributions + technical diagnostics)
                        └─ Оценка качества (benchmark)
```

Rail on desktop (labels ≥ 1280 px, icons 768–1279 px), bottom tab bar + "Ещё" sheet on phones.
The header carries context only (dataset, period, last analysis, simulation badge, theme) — it never
repeats navigation.

## Screen compositions

* **Обзор** — one sentence that says what needs attention and one primary action (open the top
  alert); four defined KPIs; daily activity (all transfers vs transfers cited by alerts) at ~64 %
  width beside the band donut; priority list and investigation-progress rings below. Every ring
  shows its denominator; with no denominator it shows "—", never 0 %.
* **Проверки** — search, kind/status/sort selects, band chips with live counts; all state in the URL.
  Wide screens preview a row in place (mini network, reasons, compact timeline); narrow screens
  open the investigation directly.
* **Расследование** — header (title, band, temporal status, priority meter, primary action);
  graph stage + context panel (summary ↔ selected account ↔ selected transfer); evidence region
  (timeline, transfer table, temporal and peer cards, technical details in a disclosure); decision
  panel aligned under the context panel. Per-kind deterministic layouts: funnel/fan-out read left to
  right, chain is a straight path in hop order, cycle is a ring.
* **Аналитика** — formations by kind (bars, with alert counts), chronology check (donut), open alerts
  by band (columns linking to the queue), case statuses (donut); hashes and versions in a disclosure.
* **Оценка качества** — headline metrics with a v1 reference tick, method comparison with a metric
  switch, per-family detection bars; full tables stay visible; ablation/robustness/sensitivity in a
  disclosure.
* **Лаборатория** — four-step flow driven only by real API and worker states; seed/precision behind
  "Параметры генерации".

## Data honesty rules followed

* New endpoint `GET /api/v1/snapshots/{id}/activity` returns per-day **counts** (not money: a
  daily sum could mix currencies) over the snapshot window, zero-filled; covered by an integration
  test that recomputes the numbers from the per-alert evidence chains.
* No invented money saved, losses, probabilities or real-time claims; the simulation badge and the
  synthetic-data notes stay on every relevant screen.
* Day-precision data never shows a clock time; the timeline states that order within a day is unknown.
* The Lab never animates mock progress: the job track reflects the persisted job status only.
