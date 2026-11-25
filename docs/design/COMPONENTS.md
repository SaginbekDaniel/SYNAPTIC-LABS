# UI components

All styling comes from `apps/web/src/styles/tokens.css`; copy from `apps/web/src/lib/i18n.ts`.

| Component | File | Use |
|---|---|---|
| `PageHeader`, `Panel`, `Disclosure`, `Segmented` | `components/ui/index.tsx` | page title + one primary action; titled surface; progressive disclosure (native `<details>`); exclusive filter/view switch (`aria-pressed`) |
| `BandBadge`, `EvidenceBadge`, `CaseStatusBadge`, `SimulationBadge` | `components/ui/index.tsx` | status with icon + text, never colour alone |
| `Stat` | `components/ui/index.tsx` | KPI: label, value, definition line, optional link |
| `Money`, `AccountId`, `TxTable` | `components/ui/index.tsx` | exact BigInt money; opaque ids verbatim (link to the graph explorer); evidence transfers with highlight/selection |
| `Loading`, `Empty`, `ErrorState`, `NoDataset` | `components/ui/index.tsx` | every data view's non-happy states |
| `Icon` | `components/ui/icons.tsx` | inline stroke icons, `aria-hidden` |
| `ActivityChart`, `SeriesLegend` | `components/charts/ActivityChart.tsx` | daily counts; solid area vs dashed line; keyboard ←/→ reading; hidden data table |
| `Donut` | `components/charts/Donut.tsx` | ≤ 5 categories; centre total; legend rows are buttons with count and share |
| `Ring`, `SegmentedMeter`, `BarList`, `ColumnChart` | `components/charts/Progress.tsx` | ratio with explicit denominator ("—" when none); 0–100 meter (`role="meter"`); horizontal bars with optional reference tick; vertical counts |
| `GraphCanvas`, `GraphLegend` | `components/graph/GraphCanvas.tsx` | Cytoscape stage with zoom/fit/focus controls; selection/highlight/theme applied without re-layout. Force layout (`layout="cose"`) runs in a worker (`coseLayout.ts`, `layoutWorker.ts`, `layoutClient.ts`): seeded and deterministic, independent of the viewport size, cached per input; the stage shows "Раскладка графа…" and draws nothing until positions exist; `data-layout="ready"` on the canvas means drawn and drivable |
| `EvidenceTimeline` | `features/investigation/EvidenceTimeline.tsx` | evidence transfers per day by direction; money only when one currency |
| `AlertPreview` | `features/alerts/AlertPreview.tsx` | queue preview with SVG mini network (no Cytoscape) |
| `SummaryView`, `AccountView`, `EdgeView` | `features/investigation/ContextPanel.tsx` | investigation side panel states |
| `CompetingExplanations` | `features/investigation/Hypotheses.tsx` | verdict, hypotheses with status, falsification tests on demand (flat disclosure, reason rows), untestable alternatives and next data |
| `CasePanel` | `features/investigation/CasePanel.tsx` | API-driven case actions, required reasons, confirmation for terminal actions, notes, audit |

Theme: `app/theme.ts` (`useTheme`, `setTheme`); dark default, light and system options; stored per
viewer in `localStorage` and applied before first paint by `index.html`.
