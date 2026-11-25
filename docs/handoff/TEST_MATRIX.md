# Test matrix

What is tested, how, where it runs, and what has **never** been executed. Counts are from runs on 2026-11-25 in a
fresh session container (L-0020) unless marked otherwise; re-measure before quoting. Full gate commands: MASTER_HANDOFF §15.

## Automated suites

| Suite | Command (from repo root unless noted) | Count 2026-11-25 | Runs in CI job | Covers |
|---|---|---|---|---|
| Python lint / format | `uv run ruff check src tests migrations` · `uv run ruff format --check src tests migrations` | clean | Lint, types, tests, E2E | style, bugbear, imports |
| Python types | `uv run mypy` | clean, 65 source files | same | `src/nexora` (strict per `pyproject.toml`) |
| Python unit + integration | `uv run pytest -p no:cacheprovider -rs` | **312 passed, 0 skipped** (296 before L-0020 + 8 progress-probe + 3 README-traceability + 5 audit allow-list tests, L-0023) | same | domain, analytics, detectors, evaluation harness, API, auth, CSRF, roles matrix, migrations, logging, handoff docs |
| Migrations | `uv run alembic upgrade head` · `uv run alembic check` · `uv run alembic heads` | single head `0005`, ORM in sync | same | chain linearity (B-001), stepwise upgrade from production's `0003` |
| Web types | `cd apps/web && npx tsc -b` | clean | same | strict TS |
| Web unit | `cd apps/web && npx vitest run` | **135 passed** (15 files) | same | graph controller, layout client/worker, gestures state machine, i18n, roles UI, formatting |
| Web build | `cd apps/web && npx vite build` | ok (largest chunk `GraphCanvas` 471 kB / 151 kB gzip) | same | bundling, lazy routes |
| OpenAPI client drift | `cd apps/web && npm run gen:api`, then `git diff --exit-code -- apps/web/openapi.json apps/web/src/lib/api-types.ts` | in sync | same | API ↔ client contract |
| Browser E2E | `cd apps/web && rm -rf node_modules/.vite && npx playwright test --trace off` | **38 passed** (2.1 min, cold cache, L-0023) | same | sign-in/out, session expiry (incl. expiry during a pending lazy navigation, H-28), roles (viewer journey), queue, investigation, cases, graph workspace, layout determinism and long-task budget, gestures with a fake camera |
| Railway definition | `cd .railway && npm ci && npm run check` | 3 services + database, all invariants hold | Deployment config | IaC invariants (no public API, gateway modes) |
| ShellCheck | CI only | — (not installed locally) | Deployment config | `scripts/*.sh` |
| Production images + gateway smoke | CI only (`docker compose` with production images) | — (no Docker daemon locally); the smoke `gestures` project ran 3/3 against `gateway_sim.mjs` (L-0023) | Production images + gateway smoke | non-root images, fail-closed gateway, rollback mode, smoke journey through the gateway, **camera path through the real Nginx: assets, CSP, fake-camera start, negative control without `'wasm-unsafe-eval'` (B-050)**, graceful worker stop |
| Pitch lint / types / unit / build | `cd apps/pitch && npm run lint && npx tsc -b && npm test && npm run build` | clean · **14 passed** (redesigned pitch, L-0021; the first pitch had 17) · ok | `pitch` workflow (path-filtered: `apps/pitch/**`, `bench-v1.json`) | pitch app; results-slide figures pinned to `bench-v1.json` |
| Pitch E2E | `cd apps/pitch && npx playwright test --trace off` | **31 passed** (L-0021) | `pitch` workflow, plus a static-server smoke test | slides, keyboard, accessibility, "no production/bank claim" guard |
| Handoff consistency | `python3 docs/handoff/probes/check_handoff_docs.py` · `python3 docs/handoff/probes/progress.py` | OK · exit 0 | via pytest | paths, commits, findings, dependency graph, status evidence |
| Dependency audit | `.github/workflows/audit.yml` (npm ×3 projects, pip-audit) with negative controls | production: npm 0, **Python 0 (first audit, run 1)**; dev npm (web): 6 (2 critical, 1 high, 3 moderate — vitest 2 / esbuild chain, B-013) | `audit` workflow (lockfile changes, weekly) | supply chain |
| CodeQL | scheduled / PR workflow | last run success (default branch, 2026-11-23) | codeql | static security analysis |

## Coverage by product area

| Area | Unit | Integration | E2E | Manual / hardware | Gap (task) |
|---|---|---|---|---|---|
| Authentication, sessions, CSRF | yes | yes | yes | — | MFA/OIDC undecided (D-6) |
| Authorization (roles) | yes | every OpenAPI operation × role | viewer journey | — | dataset isolation (B-019, D-3) |
| Ingestion / CSV import | yes | yes (gate off by default) | — | — | — |
| Detection pipeline | yes | yes | via generated datasets | — | adversarial suite (B-045), scale tests (B-047) |
| Evaluation harness / artifacts | consistency tests recompute every published ratio; README figures recomputed from artifacts | — | Evaluation screen | — | pitch shows v2 (as deployed) until B-057 |
| Graph workspace | controller, layout | graph read model | overview, local view, determinism, 300-node budget | — | relayout blank stage (B-025), SQL ranking (B-021), a11y audit (B-023) |
| Gestures (camera) | state machine, session order | — | fake camera (Chromium) | **never run on a real hand** | B-030 (human), B-032, B-033 |
| Gateway / deployment | — | — | CI smoke through production images, incl. the camera path (B-050) | live Railway never inspected by an agent | B-005, B-055 |
| Logging | JSON formatter, request id | forced 500 / DB error | server log lines parse as JSON | — | job events (B-016) |
| Transfer protection (collaborator branch) | on its branch only | on its branch only | on its branch only | — | not integrated (B-056, H-26) |

## Never executed (as of 2026-11-25)

Real webcam (B-030) · Docker build/compose locally (CI runs it) · `pip-audit` locally (CI runs it) · live Railway state (B-005) · ORM load/publish at 200k rows (B-047) · penetration test · backup/restore drill (B-051) · any real
banking data (never in scope).
