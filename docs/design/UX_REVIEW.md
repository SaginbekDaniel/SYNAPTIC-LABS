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

## Known limitations (not fixed here)

* The queue loads at most 200 alerts (API page limit); search and band counts apply to those.
* On phones the graph is legible but small; focus mode (full screen) is the intended path.
* Very large funnels (20+ feeders) form a dense column; labels shrink with zoom.
* Canvas nodes are not individually keyboard-focusable; the "Все счета формации" list is the keyboard path to the same selection.
* The Web Interface Guidelines rule list was not fetched live (see `SKILLS_USED.md`).

## Verification run

* `npx tsc -b`, `npx vitest run` (22 tests), `npx vite build`
* `npx playwright test` — 10 tests (5 existing journeys, 4 new redesign tests, 1 mobile overflow/order test)
* `uv run ruff check src tests migrations`, `uv run mypy`, `uv run pytest` (incl. the new activity endpoint test)
