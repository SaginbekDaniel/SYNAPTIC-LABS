# UX acceptance review

Run against the real stack (PostgreSQL, API, worker, Vite) with `demo-v1 · seed 2026`, in Chromium
at 1440, 1280, 768 and 390 px, dark and light. Interaction counts start from the screen named.

| Journey | Path | Interactions | Result |
|---|---|---|---|
| A. First-time analyst understands what needs attention | Обзор | 0 | Page sentence: "7 алертов ждут проверки. Начните с самого приоритетного." + one primary button; on phones the priority list comes first |
| B. Find a high-priority network | Обзор → "Открыть приоритетный алерт", or Проверки → band chip "Высокий" | 1 | Band chips show counts; filter is in the URL and survives reload (E2E) |
| C. Understand why, without reason codes | Investigation context panel | 0 | Plain-language hypothesis, then "Подтверждает" / "Ослабляет" / "Чего система не знает" / "Что проверить дальше" |
| D. Verify evidence | Graph node or participant → account panel; edge → transfer panel; "Показать транзакции" | 1 each | Selection dims the rest of the graph, highlights rows in the table, marks days on the timeline; each transfer lists amount, currency, sender, receiver, date (with precision) and the reasons that cite it |
| E. Record a decision | "Открыть расследование" → choose action → reason → "Записать действие" (+ confirm for terminal actions) | 3–4 | Allowed actions come from the API; reasons required where the API requires them; saved-state message; header status refreshes; audit log appends (E2E) |
| F. Find benchmark results | Аналитика → "Оценка качества" | 2 | Headline metrics with v1 reference, comparison chart, then tables; experiments collapsed |

## Problems found during review and fixed

* Focus ring drawn around `<main>` on first load (StrictMode re-ran the "skip first navigation" effect) → compare against the last pathname.
* Y-axis ticks 6/13/19 → round tick steps.
* Hidden data tables and an absolutely positioned hidden header label escaped their scroll containers and caused horizontal scroll on phones → wrapper div + positioning context on `.table-wrap`.
* Key/value labels claimed `max-content` and squeezed values to one character at 1280 px → `fit-content(50%)` label column.
* Account IDs broke mid-number in tables → no wrapping inside table cells (tables scroll).
* Queue preview's primary button was below the fold → moved under the title.
* Decision copy called "Закрыть" a final decision, but the API records a judgement only for escalate/dismiss → copy now matches the state machine.
* Lab suite descriptions arrived in English from the API → localised in the catalogue with API fallback.
* Tablet overview placed the priority list last → directly under the activity chart.

## Release polish pass (second review)

CI: run 44088061005 failed at `ruff format --check` on `src/nexora/application/queries.py:346`
(a call split over three lines that fits the configured line length). Fixed by running the
formatter; no logic change.

Reviewed against the real stack (PostgreSQL, API, worker, Vite) with `demo-v1 · seed 2026` and a
CSV-imported review dataset of 1 020 synthetic transfers (55 alerts, three 24–25-account funnels),
in Chromium at 390, 768, 1280 and 1440 px, dark and light. Every screen was screenshotted full-page
and checked programmatically for horizontal overflow and console errors (none).

| Problem found | Root cause | Fix |
|---|---|---|
| Queue could misrepresent its results: it loaded at most 200 alerts and computed band counts, search and sort locally | The API had paging but no search, sort or facet counts, so the client worked around it | `GET /api/v1/alerts` gains `q` (case-insensitive substring of any member account, LIKE-escaped), `sort` (`priority`/`accounts`/`transfers`/`recent`, applied before paging) and `band_counts`/`kind_counts` facets over the whole filtered set (additive, backward compatible). The queue now requests 50 per page, keeps every filter, the search, the sort and the page in the URL, shows "1–50 из 55" / "Найдено: N" and a pager. The previous page stays visible (dimmed, `aria-busy`) while the next loads |
| Analytics "alerts per kind" counted only the first 200 alerts | Same 200-item page | Uses `kind_counts` (limit 1) |
| Overview priority list could empty out when many alerts were closed | It fetched the top 12 of all statuses and filtered closed ones client-side | Fetches open and in-case alerts (5 each) and merges them in the API's queue order |
| 24-feeder funnel drawn as a ~1 000 px single column; fit-to-view shrank labels to ~5 px | `layoutFlow` stacked every source in one column | Groups larger than 8 wrap into staggered columns away from the hub; nodes and edges are unchanged |
| On phones the graph was a thin strip in the portrait stage | Landscape layout in a ~330×380 stage | Below 768 px flow and chain layouts read top to bottom (positions only) |
| Stage hint said details appear "справа" on stacked layouts, where they appear below | One hint for all layouts | Separate hint below 1 100 px |
| 390 px queue: filter selects truncated ("Все стату…", "По приор…") and used 13 px text, which makes iOS Safari zoom on focus | Three selects in one row with a font-size override that beat the 16 px phone rule | Two selects per row, sort full width, 16 px |
| Analytics column chart labels ran into each other ("КритическийВысокий") at 1280 px | Long single words in narrow columns | Hyphenation / break-word |
| Temporal donut legend truncated status names | `nowrap` + ellipsis | Names wrap |
| Light theme kept the dark `theme-color`, so the iOS/PWA toolbar stayed black | Static meta tag | Synced with the active `--canvas` token (inline script before paint and on every theme change) |

Keyboard: verified in the browser that Tab reaches the graph controls, each "Показать транзакции"
button and the "Все счета формации" disclosure; Enter on an account there opens it in the context
panel, which is the same selection as clicking a canvas node.

## Known limitations (not fixed here)

* Canvas nodes are not individually keyboard-focusable; the account list is the keyboard path.
* On phones a 25-account funnel fits the stage but labels are still small; pinch-zoom or focus mode
  (full screen) is the intended way to read it.
* Queue search matches account ids only (formation type has its own filter); it is a substring
  match without an index, which is fine at demo scale but would need a trigram index for large data.
* Docker images were not built in this environment; `docker compose config` validates, and the
  same stack (PostgreSQL 16, migrations, API, worker, Vite) was run directly.

## Verification run

* `npx tsc -b`, `npx vitest run` (26 tests, adds queue-order merge and graph layout tests), `npx vite build`
* `npx playwright test` — 11 tests (adds server-side queue search by member account)
* `uv run ruff check src tests migrations`, `uv run ruff format --check src tests migrations`, `uv run mypy`, `uv run alembic upgrade head && uv run alembic check`, `uv run pytest` (99 tests, adds alert paging/search/sort/facet contract test)
* `npm run gen:api` — regenerated and committed `openapi.json` and `src/lib/api-types.ts`
