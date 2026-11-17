# Design skills used in the NEXORA redesign

Sources were cloned read-only into a session scratch directory and their `SKILL.md`
files read in full before any UI code was written. Nothing was installed globally.
The entry point was the `find-skills` instructions (`npx skills use https://github.com/vercel-labs/skills --skill find-skills`).

| Skill | Source actually read | Status |
|---|---|---|
| Frontend Design | `anthropics/skills` → `skills/frontend-design/SKILL.md` (the plugin linked in the brief now lives here; `anthropics/claude-code/plugins` only holds a README) | applied |
| UI/UX Pro Max | `nextlevelbuilder/ui-ux-pro-max-skill` → `.claude/skills/ui-ux-pro-max/SKILL.md` + `scripts/search.py` | applied, search tool executed |
| Web Design Guidelines | `vercel-labs/agent-skills` → `skills/web-design-guidelines/SKILL.md` | applied as an audit checklist (see note) |
| React Best Practices | `vercel-labs/agent-skills` → `skills/react-best-practices/SKILL.md` | applied |

## Frontend Design — what was applied

* **Two-pass process**: a compact token plan (palette, type, layout, principles) was drafted and
  reviewed against the brief before coding; see `DESIGN_DIRECTION.md`.
* **"Spend your boldness in one place"**: the investigation graph stage is the only expressive
  surface (dot grid, soft violet radial glow, glowing subject node). Everything else is quiet panels.
* **Avoided the listed generic tells**: no ALL-CAPS eyebrow labels (the old table group headers
  were uppercase — removed), no monospace for small data labels (mono is used only for account and
  transaction identifiers, where character-exactness matters), no `→`-suffixed link text, no
  single-word accent colouring in headlines, numbered markers only where content is a real sequence
  (the Lab stepper, the "what to check next" list).
* **Typography as a choice**: Onest (a Cyrillic-native grotesque) instead of a default system/Inter stack.
* **Writing**: copy rewritten from the analyst's perspective ("Почему это подозрительно",
  "Чего система не знает", "Что проверить дальше"); actions keep one name through the flow
  ("Записать действие" → status "Записано в журнал: …"); empty states say what to do next.
* **Quality floor**: visible focus everywhere, `prefers-reduced-motion` honoured (tokens zero all
  durations), self-critique with screenshots after every pass.

## UI/UX Pro Max — searches executed and how results were used

Run with `python3 -I scripts/search.py …` (isolated mode, no project data in queries).

| Query | Result used | Result rejected |
|---|---|---|
| `"fintech fraud investigation analytics dashboard dark" --design-system --density 8 --variance 6 --motion 3` | Dark-mode style; dense dashboard spacing scale; pre-delivery checklist (focus states, reduced motion, 375/768/1024/1440 checks, 150–300 ms transitions) | "Enterprise Gateway" landing-page pattern (marketing, not an app); green CTA accent (conflicts with the brief's violet); GSAP scroll reveals (motion for its own sake) |
| `"banking fintech dark violet" --domain color` | Confirmed violet + cyan on near-black as an established pairing (`#7C3AED`/`#0891B2`-family); `rgba(255,255,255,0.08)` borders → our `--line` | — |
| `"dashboard data analytics numbers" --domain typography` | Need for tabular figures and a precise sans | Fira Code headings (mono headings are a generic tell per Frontend Design) |
| `"risk distribution part to whole" --domain chart` | Donut only for ≤ 5 categories, every slice labelled with count and %, legend doubles as accessible fallback, keyboard reach to each slice | Pie without labels |
| `"time series trend volume" --domain chart` | Line/area for daily counts; distinct line *styles* (solid area vs dashed line), not hue alone; data table fallback; keyboard reading of points | Candlestick (no OHLC data) |
| `"sidebar navigation hierarchy active state" --domain ux` | Clear active state in rail and tab bar; breadcrumb-style back link only on the one deep level (investigation) | — |
| `"dark mode contrast" --domain ux` | 4.5:1 minimum: violet fill darkened to `#7C5CE6` so white button text passes (4.6:1); muted text `#80859B` on `#10111A` ≈ 5:1 | — |
| `"data table filter sort" --domain ux` | Tables keep horizontal scroll inside their own container; phones get card rows instead | Bulk actions (no bulk API) |

## Web Design Guidelines — note on use

The skill's instructions are to fetch the live rule list from
`raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md` before each review.
That fetch was **not** performed in this session; the audit was run against the rule categories the
skill names (accessibility, forms, navigation, interaction, typography, responsiveness, states), and
these concrete checks were made in a real browser:

* skip link; focus moves to `<main>` only on real route changes (not on first load);
* every icon-only control has an `aria-label` (graph zoom/fit/focus, sheet close, theme buttons);
* form fields have visible labels; required reasons are announced via `aria-required` + help text;
* inputs are 16 px on phones (prevents iOS zoom); controls ≥ 44 px in the phone tab bar and sheet;
* no horizontal page overflow at 390/768/1280/1440 (checked programmatically on every screen);
* loading (skeleton), empty (with next action), error (code + request id + retry) states on every data view;
* destructive/terminal case actions require an inline `alertdialog` confirmation.

## React Best Practices — rules applied

| Rule | Where |
|---|---|
| `async-parallel` | Overview and Analytics fetch all independent endpoints with one `Promise.all` |
| `bundle-dynamic-imports` / `bundle-conditional` | Investigation, Network, Analytics, Benchmark and Lab are lazy routes; Cytoscape stays in its own chunk; the queue's network preview is plain SVG so the queue never loads Cytoscape |
| `rerender-derived-state-no-effect` | Queue band counts, filtering and sorting are derived with `useMemo`, not effects |
| `rerender-use-deferred-value` | Queue search uses `useDeferredValue` |
| `rerender-move-effect-to-event` | Row preview/selection handled in click handlers |
| `js-set-map-lookups` | Highlighted edges / roles via `Set`/`Map` (removed an O(n²) `find` in the canvas) |
| `rendering-svg-precision` | Chart paths rounded to 2 decimals |
| `rendering-hydration-no-flicker` | Theme applied by an inline script in `index.html` before first paint |
| `client-event-listeners` | `useSyncExternalStore` for media queries and theme (one subscription per hook) |
| Performance of graph interactions | Cytoscape instance is built once per element set; selection, highlight and theme are applied as classes/styles on the live instance (previously every highlight toggle destroyed and re-laid-out the graph) |
