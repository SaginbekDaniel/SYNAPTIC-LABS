# NEXORA AI — Graph Workspace & Gesture Control: handoff to Zencoder

Prepared 2026-11-21 from a fresh clone, by re-running every check listed in §10 in a Linux
container (Python 3.13, Node 22, PostgreSQL 16, Chromium via Playwright). Nothing below is copied
from earlier reports without being re-verified; anything not executed is marked **not executed**.

Companion documents: [`ZENCODER_TASKS.md`](ZENCODER_TASKS.md) (actionable task list) and
[`ZENCODER_EXECUTION_PROMPT.md`](ZENCODER_EXECUTION_PROMPT.md) (self-contained prompt to start a
Zencoder session). Project rules that bind all work: [`/CLAUDE.md`](../../CLAUDE.md) and the P0
gates in [`/NEXORA_AI_MASTER_SPEC_CLAUDE_CODE.md`](../../NEXORA_AI_MASTER_SPEC_CLAUDE_CODE.md).

---

## 1. Product overview and objectives

NEXORA AI is an explainable financial-network investigation tool (fraud / AML triage) built by
SYNAPTIC LABS for the ITU Hackathon 2026 (Bank CenterCredit case). It turns transfers into
evidence-backed, time-consistent, coverage-aware network "formations" (funnel, fan-out, chain,
cycle), ranks them for a human analyst, and records the analyst's case decisions with an audit
trail. **Synthetic data only, no banking integration, no automatic action against customers, no LLM
in the evidence pipeline.**

This handoff covers the newest feature set on branch `graph-workspace-wip`:

* **Graph Workspace** (`/network`): an investigation graph over a *stored* analysis snapshot —
  overview of the top formations (server-ranked) or the 1–2 hop neighbourhood of one account, with
  URL-backed filters, bounded expansion, a table fallback and exact edge drill-down to source
  transactions.
* **Gesture Control** (opt-in, off by default): drive the same graph with hand gestures through the
  webcam. Recognition runs entirely in the browser (MediaPipe Hand Landmarker in a Web Worker); no
  frame or landmark leaves the device; gestures can only navigate/select (and, in an explicit mode,
  move nodes) — never change a case.

Objective for the next phase: take the feature from "verified checkpoint" to "mergeable and
deployable" — documentation, dependency security, the hardware verification that automation cannot
do, and the integration of the stacked open PRs (see §6).

## 2. Architecture and technology stack

| Layer | Technology | Notes |
|---|---|---|
| Web | React 18, TypeScript 5.9, Vite 5.4, react-router 6, Cytoscape.js 3.35 | `apps/web`; served in production by unprivileged Nginx (gateway) |
| Gestures | `@mediapipe/tasks-vision` **1.2.2 (pinned exactly)** in a module Web Worker | WASM + `hand_landmarker.task` self-hosted under `/vendor/mediapipe/`, SHA-256 pinned |
| API | FastAPI, Pydantic v2 | OpenAPI → generated TS client (`apps/web/openapi.json`, `src/lib/api-types.ts`) |
| Analysis | Python 3.13, NetworkX, exact integer money | `nexora.analytics` is pure (no FastAPI/SQLAlchemy imports) |
| Jobs | PostgreSQL lease worker (`FOR UPDATE SKIP LOCKED`) | at-least-once, idempotent publish (content-derived uuid5 ids) |
| Storage | PostgreSQL 16, SQLAlchemy 2, Alembic | `NUMERIC(38,0)` money; append-only audit via trigger |
| Auth | Named accounts (Argon2id), server-side sessions in PostgreSQL, CSRF token | every `/api` route requires a session except login/session |
| Delivery | Docker / Compose, GitHub Actions, Railway IaC (`.railway/railway.ts`) | deploys are manual and approval-gated |

### Graph Workspace data flow

```
GET /api/v1/snapshots/{id}/graph  (graph-view-v1, src/nexora/application/graph_view.py)
  mode=overview : top formations by STORED band/priority, whole formations only (+ transfers among them)
  mode=local    : 1–2 hop transfer neighbourhood of account_id
  → limits {effective budgets, formations_total, reasons}  + snapshot/dataset/policy/config/input hashes
GET /api/v1/snapshots/{id}/edge-transactions  → exactly the transactions aggregated into one edge

GraphWorkspace.tsx ──toCanvas(graph, clientFilters)──▶ GraphCanvas.tsx (Cytoscape, seeded cose layout)
                                                        └─ GraphController (typed command pipeline)
                                                             ▲            ▲            ▲
                                                           mouse       keyboard     GestureAdapter
```

* **GraphController** (`apps/web/src/components/graph/controller.ts`) is the only way anything moves
  the graph. Its command union (`pan, zoomAt, zoomStep, resetView, focusNode, selectNode,
  selectEdge, hover, hoverEnd, dragStart, dragMove, dragEnd, cancel, expandNeighborhood`) is pinned by
  a unit test so no write command can be added silently. A cancelled drag restores the node's model
  position exactly.
* Risk shown in the graph is always the **stored** assessment; the graph endpoint never scores.

### Gesture pipeline

```
CameraSession (getUserMedia, state machine)
  → HandLandmarkEngine (main thread; ≤1 frame in flight, frames dropped not queued, 480 px wide, ≤30/s)
     → landmarkWorker.ts (module worker: same-origin network guard + stderr routing, then MediaPipe)
  → GestureRecognizer (pure state machine: hold times, hysteresis, pinch reach check vs fist,
                        cooldown, cancel on hand loss/ambiguity; One Euro smoothing)
  → GestureAdapter ("navigate" never moves nodes; "arrange" allows drag)
  → GraphController
GestureSession (gestureSession.ts) owns the lifecycle and is an external store for React.
```

Every exit path (button, Esc, hidden tab, route change/unmount, camera loss, engine failure) goes
through `GestureSession.stop()`, which cancels the active gesture, stops camera tracks and disposes
the worker. Restarting always needs a new, deliberate click.

## 3. Repository structure and entry points

```
apps/web/                         React SPA + gateway image
  src/app/App.tsx                 routes; /network → features/graph/GraphWorkspace (lazy)
  src/features/graph/             GraphWorkspace.tsx, graphModel.ts (+ test)
  src/components/graph/           GraphCanvas.tsx, controller.ts (+ test), canvasColor.ts (+ test)
  src/features/gestures/          GestureControl.tsx (UI), gestureSession.ts, cameraSession.ts,
                                  landmarkEngine.ts, landmarkWorker.ts, recognizer.ts, adapter.ts,
                                  landmarks.ts, oneEuro.ts, sameOriginGuard.ts, workerConsole.ts,
                                  syntheticHands.ts (+ unit tests)
  src/lib/i18n.ts                 ALL user-facing copy (Russian dictionary)
  src/styles/tokens.css           ALL colours/spacing (design tokens)
  scripts/gesture-assets.mjs      Vite plugin: copies/downloads + SHA-256-verifies MediaPipe assets
  docker/csp.mjs                  generates the gateway CSP/security headers at image build
  docker/default.conf.template    Nginx gateway (/vendor/ → try_files =404)
  e2e/graph-workspace.spec.ts     graph E2E;  e2e/gestures.spec.ts  gesture E2E
  playwright.config.ts            projects: setup, desktop, mobile, auth, gestures
src/nexora/
  api/routes/analysis.py          /snapshots/{id}/graph, /edge-transactions, /neighborhood
  application/graph_view.py       graph read model (overview/local, budgets, evidence edges)
  auth/                           sessions, passwords, CLI
  analytics/, domain/             pure analysis (no web/DB imports)
migrations/versions/0001…0004     Alembic chain (head = 0004)
tests/integration/test_investigation_graph.py   graph API integration tests
apps/pitch/                       separate static pitch deck (own CI workflow)
docs/implementation/GRAPH_GESTURE_VERIFICATION.md   manual real-camera checklist (not yet executed)
```

Run entry points: `make api`, `make worker`, `make web` (see §8); production: `docker compose up`.

## 4. Implemented functionality (verified by executed tests, §10)

**Graph Workspace**
* Overview/local modes; URL-backed server filters (band, kind, mode, account, depth) that survive
  reload; client-side edge filters (temporal status, evidence-only, currency).
* "25 of N formations by priority" via `limits.formations_total`; truncation reasons shown.
* Bounded, race-safe expansion of a node's neighbourhood (refuses to splice in a different
  snapshot; stale expansions aborted on view change).
* Deterministic layout: same snapshot → same picture (seeded positions, `randomize: false`).
* Keyboard navigation (`[`/`]` cycle, Enter select) with a live region; table fallback; exact edge
  drill-down whose totals recompute from the listed transactions; formation highlighting; light/dark
  themes; narrow widths.
* Band colour from stored risk; formation hubs as diamonds; dotted line = contradicted chronology.

**Gesture Control**
* Consent dialog before any browser camera prompt; denial leaves mouse/keyboard fully usable.
* Real MediaPipe recognition in a worker, model + WASM self-hosted and hash-verified; zero
  cross-origin requests (guard in the worker + gateway `connect-src 'self'`).
* Gestures: open palm = pan, index = point/hover, short pinch = select, pinch-move = drag
  (*Расстановка* mode only), two-hand pinch = zoom; Esc / button stop; dominant hand selectable.
* Camera released on Esc, stop, hidden tab, route change, unmount, camera loss, engine failure.
* Disabled on devices without a fine pointer (phones keep the touch interface) or without
  `getUserMedia`/`Worker`.

**Fixed in this handoff session** (root causes, with tests):
1. *Gesture E2E failed deterministically on a cold Vite cache* (i.e. on every CI run): the worker
   imports MediaPipe lazily, Vite's dev dependency scan did not see it, so first use triggered
   "optimized dependencies changed. reloading" — a full page reload mid-session that reset the
   gesture state to "off". Fix: `optimizeDeps.include: ["@mediapipe/tasks-vision"]`
   (`apps/web/vite.config.ts`). Reproduced before, verified after with `node_modules/.vite` deleted.
2. *Console error from the worker in development*: the guard deleted `WebSocket`, so Vite's HMR
   client inside the worker threw. Fix: the guard now applies one same-origin rule to fetch, XHR,
   **WebSocket and EventSource** (ws/wss mapped to http/https for the origin comparison) instead of
   removing sockets. Cross-origin sockets are still blocked (unit-tested).
3. *MediaPipe logs a healthy start as an error* ("INFO: Created TensorFlow Lite XNNPACK delegate
   for CPU." via `console.error`, because Emscripten binds stderr to `console.error` at load).
   Fix: `workerConsole.ts` routes only lines starting with `INFO: ` to `console.info`, installed
   before MediaPipe loads. Real errors still reach `console.error` (unit-tested).
4. *Graph edges silently rendered in Cytoscape's default grey*: tokens use CSS Color 4
   (`--g-edge: rgb(163 167 200 / 0.38)`), which Cytoscape's parser rejects ("style property … is
   invalid"). Fix: every colour token entering the Cytoscape stylesheet goes through
   `toCanvasColor()` (`canvasColor.ts`), converting to `rgba(r, g, b, a)`; verified 0 warnings in
   the browser and visually.
5. Dangling reference: `e2e/gestures.spec.ts` cited `docs/implementation/GRAPH_GESTURE_VERIFICATION.md`,
   which did not exist. Created as a checklist explicitly marked *not yet executed*.

## 5. Incomplete functionality

| Area | State |
|---|---|
| Real-camera verification | **Never performed.** Automated tests use a synthetic camera (no hand) and a scripted landmark worker. Checklist: `docs/implementation/GRAPH_GESTURE_VERIFICATION.md`. Recogniser thresholds are untuned on real hands. |
| Documentation | README, `docs/ARCHITECTURE.md`, `SECURITY.md`, `docs/LIMITATIONS.md`, `docs/INTERFACES.md`, CHANGELOG do not describe the Graph Workspace or the camera mode. README still says PR #3 is "open, not merged" although this branch merges it. |
| Security documentation | Camera/privacy model (consent, local processing, CSP `wasm-unsafe-eval` + `worker-src 'self'`, `Permissions-Policy camera=(self)`, worker network guard) is only in code comments. |
| Production image | `docker build apps/web` **not executed** here (no Docker daemon). The image build downloads `hand_landmarker.task` from `storage.googleapis.com` at build time and fails closed on hash mismatch — the build host needs that egress. |
| Deployment | Not deployed. The live Railway demo runs an older build without the graph workspace. |
| Pitch | `apps/pitch` not updated for the graph workspace/gestures (optional). |
| Graph stage layout | At 1440×900 the filter panel pushes the graph stage mostly below the fold (stage starts ≈ y 580). UX polish, not a defect in function. |
| Localisation | Only the Russian dictionary exists (by spec). New copy must still go through `i18n.ts`. |

## 6. Relevant commits and branches

GitHub: https://github.com/SaginbekDaniel/SYNAPTIC-LABS — **default branch is
`claude/brave-dirac-c80nwq`** (not `main`; there is no `main`).

| Ref | What |
|---|---|
| `ea5ca9c` | Default branch head (`Merge pull request #4`) |
| `3b0b558` | Local merge of PR #15 — named-account sign-in, sessions, CSRF (**PR still open on GitHub**) |
| `8a02f95` | Local merge of PR #3 — leakage fixes, hypothesis engine v1, sealed evaluation (**PR still open**) |
| `f9f1a78` | Local merge of PR #5 — `apps/pitch` (**PR still open**) |
| `ff40b72` | Investigation graph read model (`/graph`, `/edge-transactions`) |
| `b9943f0` | Checkpoint: graph workspace, GraphController, opt-in camera gestures (WIP) |
| this commit | Root-cause fixes listed in §4 + handoff documents (`git log -1 graph-workspace-wip`) |

Branches: `graph-workspace-wip` (this work, pushed fast-forward), `claude/peaceful-darwin-nrquu9`
(same commits; the session branch it was prepared on). Open PRs #6–#14 are Dependabot bumps
(several are the major upgrades in §12). **Consequence:** a PR from `graph-workspace-wip` to the
default branch would also land PRs #3, #5 and #15. Either merge those first (in the order 15 → 3 →
5) or open the graph PR knowingly as a stack — the repository owner decides.

## 7. Database and migration requirements

* PostgreSQL 16. Alembic chain `0001 → 0002 → 0003 → 0004` (head `0004`):
  `0003_auth_users_sessions` (users, sessions, sign-in attempts), `0004_hypothesis_assessments`.
* The Graph Workspace and gestures add **no migration**; they read published snapshots,
  formations, assessments, evidence and transactions.
* Verified: `alembic upgrade head` on an empty DB, then `alembic check` → "No new upgrade
  operations detected" (ORM and migrations agree).
* Integration tests and E2E reset their own disposable databases (`scripts/reset_disposable_db.py`);
  never point `NEXORA_TEST_DATABASE_URL`/`NEXORA_E2E_DATABASE_URL` at a database you care about.
* Migration `0002` refuses downgrades that would discard published analyses — do not "fix" that.

## 8. Local development setup

```bash
# PostgreSQL 16 running locally, then once:
psql -U postgres -c "CREATE ROLE nexora LOGIN PASSWORD 'nexora' CREATEDB"
for db in nexora nexora_test nexora_e2e; do createdb -U postgres -O nexora "$db"; done
make setup          # uv sync --frozen && (cd apps/web && npm ci)
make migrate        # alembic upgrade head
uv run python -m nexora.auth.cli create-user analyst --generate   # prints a password once
make api            # :8000
make worker
make web            # :5173, proxies /api
```

Then: sign in → **Лаборатория** → generate → *Запустить анализ* → **Граф связей**. Production-like:
`docker compose up --build -d --wait` (http://127.0.0.1:8080). Details:
`docs/development/local-setup.md`.

Gesture assets: the first `vite`/`vite build` writes `apps/web/public/vendor/mediapipe/`
(git-ignored): WASM copied from `node_modules`, the model downloaded once from
`storage.googleapis.com` and SHA-256-verified. Dev server only warns if the download fails
(gesture mode then reports the model is unavailable); production builds fail.

## 9. Environment variables and external dependencies (names only)

API/worker (`NEXORA_` prefix, defaults in `src/nexora/settings.py`, documented in `.env.example`):
`NEXORA_DATABASE_URL`, `NEXORA_CORS_ORIGINS`, `NEXORA_TRUSTED_ORIGINS`,
`NEXORA_SESSION_IDLE_MINUTES`, `NEXORA_SESSION_ABSOLUTE_HOURS`, `NEXORA_SESSION_COOKIE_SECURE`,
`NEXORA_LOGIN_WINDOW_MINUTES`, `NEXORA_LOGIN_MAX_FAILURES_PER_USER`,
`NEXORA_LOGIN_MAX_FAILURES_PER_CLIENT`, `NEXORA_BOOTSTRAP_USERNAME`,
`NEXORA_BOOTSTRAP_PASSWORD_HASH`, `NEXORA_EXPOSE_API_DOCS`, `NEXORA_GATEWAY_TOKEN`,
`NEXORA_DB_POOL_SIZE`, `NEXORA_DB_MAX_OVERFLOW`, `NEXORA_MAX_UPLOAD_BYTES`, `NEXORA_MAX_CSV_ROWS`,
`NEXORA_JOB_LEASE_SECONDS`, `NEXORA_JOB_MAX_ATTEMPTS`, `NEXORA_WORKER_POLL_SECONDS`,
`NEXORA_BIND_HOST`, `PORT`. Graph caps (settings fields, overridable as `NEXORA_GRAPH_MAX_*`):
`graph_max_depth`=3, `graph_max_nodes`=300, `graph_max_edges`=1500, `graph_max_formations`=40.

Gateway: `NEXORA_GATEWAY_AUTH` (`session`|`basic`|`off`), `NEXORA_GATEWAY_USER`,
`NEXORA_GATEWAY_PASSWORD`, `NEXORA_API_UPSTREAM`, `NEXORA_GATEWAY_TOKEN`. Compose: `POSTGRES_PASSWORD`.

Tests: `NEXORA_TEST_DATABASE_URL`, `NEXORA_E2E_DATABASE_URL`, `NEXORA_E2E_PASSWORD` (test-only),
`NEXORA_API_URL` (Vite proxy target). Smoke: `NEXORA_SMOKE_USER`, `NEXORA_SMOKE_PASSWORD`.

External dependencies: `storage.googleapis.com` (model download **at build time only**); npm
registry; PyPI; Railway (deployment). At runtime the browser contacts only its own origin.

## 10. Verification commands and observed results (2026-11-21, this container)

| Check | Command | Result |
|---|---|---|
| Ruff lint | `uv run ruff check src tests migrations` | All checks passed |
| Ruff format | `uv run ruff format --check src tests migrations` | 87 files already formatted |
| mypy | `uv run mypy` | no issues in 61 source files |
| pytest (unit + integration, live PostgreSQL) | `uv run pytest` | **190 passed, 0 skipped**, 1 deprecation warning (starlette/httpx) |
| Graph API integration | `uv run pytest tests/integration/test_investigation_graph.py` | 7 passed |
| Migrations | `uv run alembic upgrade head && uv run alembic check` | head 0004; no new operations |
| OpenAPI drift | `cd apps/web && npm run gen:api && git diff --exit-code -- openapi.json src/lib/api-types.ts` | no diff |
| TypeScript | `cd apps/web && npx tsc -b` | clean |
| Vitest | `cd apps/web && npx vitest run` | **99 passed (12 files)** (93 before this session; +6 new) |
| Production build | `cd apps/web && npx vite build` | built; assets SHA-256 verified; worker chunk + `vision_bundle` emitted |
| Playwright full suite | `cd apps/web && rm -rf node_modules/.vite && npx playwright test --trace off` | **34 passed** (setup 1, auth 10, desktop 18, mobile 1, gestures 4) |
| Graph workspace E2E | (desktop project, `e2e/graph-workspace.spec.ts`) | 5 passed |
| Gesture E2E | `npx playwright test --project=gestures` | 4 passed (before the fix: 1 failed deterministically on a cold cache) |
| Production bundle under gateway CSP | full Playwright suite against `dist/` served with exactly the headers from `docker/csp.mjs` (scratch Node server standing in for Nginx; not committed) | **34 passed**, no CSP violations (tests assert an empty console-error list) |
| IaC | `cd .railway && npm ci && npm run check` | 3 services + database, all invariants hold |
| Pitch app | `cd apps/pitch && npm run lint && npx tsc -b && npm test && npm run build && smoke && npx playwright test` | lint clean, 17 unit, smoke passed, 29 E2E passed |
| npm audit (web) | `cd apps/web && npm audit` | 8 advisories (2 critical, 1 high, 5 moderate) — see §12 |
| ShellCheck | `shellcheck scripts/*.sh scripts/railway/*.sh apps/web/docker/*.envsh` | **not executed** (not installed in this environment; no shell script changed) |
| Docker image build / compose / gateway smoke | `docker compose up --build` + `playwright.smoke.config.ts` | **not executed** (no Docker daemon) |
| Python dependency audit (pip-audit) | — | **not executed** (tool not available) |
| Real webcam | `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` | **not executed** |

## 11. Known bugs and reproduction steps

| # | Issue | Reproduce | Severity |
|---|---|---|---|
| B1 | `react-router-dom` 6.30.6 advisories (open redirect via backslash in `<Link>`/`useNavigate`, GHSA-wrjc-x8rr-h8h6; SSR deserialisation GHSA-337j-9hxr-rhxg — SSR not used). Only fix is v7 (major). | `cd apps/web && npm audit` | moderate, ships to production |
| B2 | Dev/test-only advisories: vite ≤ 6.4.3 (dev-server path traversal etc.), esbuild ≤ 0.24.2, vitest ≤ 4.1.10 / tinypool / @vitest/mocker (critical only when the Vitest UI/API server listens). Fixes are majors (vite 8, vitest 5). | `npm audit` | dev-only; do not expose the dev server |
| B3 | Graph stage below the fold at 1440×900; filters take ~300 px. | Open `/network` at 1440×900 | UX |
| B4 | Cytoscape logs "You have set a custom wheel sensitivity" on every graph mount. | Open `/network`, DevTools console | cosmetic |
| B5 | React Router v7 future-flag warnings in the console. | Any page, dev build | cosmetic (resolved by B1) |
| B6 | README states PR #3 is open/unmerged and its numbers not yet applicable, but this branch contains it; README/ARCHITECTURE/SECURITY lack the graph and camera features. | Read README "Evaluation" warning | docs |
| B7 | `apps/web` has no ESLint (only `tsc`); `apps/pitch` has one. | — | tooling debt |
| B8 | Recogniser thresholds unvalidated on real hands; possible false pinches or missed gestures under poor lighting. | Requires a webcam; see checklist | unknown until tested |

No failing automated check remains.

## 12. Security considerations

* **Camera**: off by default; consent dialog precedes the browser prompt; camera released on every
  exit path; restarting needs a new click; hidden tab stops it. Frames/landmarks never leave the
  worker/page; nothing is stored or logged.
* **Network isolation of MediaPipe**: MediaPipe 1.2.x uploads usage metrics to a Google endpoint
  by design. Two independent layers stop it: the worker's same-origin guard (fetch, XHR,
  WebSocket, EventSource) and the gateway CSP `connect-src 'self'`. E2E asserts zero foreign
  requests, including after stop (when MediaPipe flushes metrics).
* **CSP**: `script-src 'self' 'wasm-unsafe-eval' <sha256 of inline scripts>` (WASM compilation
  only — not `eval`), `worker-src 'self'`, `default-src 'self'`, `frame-ancestors 'none'`.
  `Permissions-Policy: camera=(self)`, everything else denied.
* **Supply chain**: `@mediapipe/tasks-vision` pinned to an exact version (integrity in
  `package-lock.json`); copied WASM and downloaded model are SHA-256-pinned in
  `scripts/gesture-assets.mjs`; production builds fail closed on mismatch; `/vendor/` returns 404 for
  missing files (never the SPA's `index.html`). Upgrading MediaPipe requires deliberately updating
  the version and all three hashes.
* **Read-only gestures**: the `GraphController` command union has no write commands (pinned by a
  test). Gestures cannot change cases, assessments or data.
* **API**: `/graph` and `/edge-transactions` require a session (covered by the anonymous-rejection
  route enumeration test); budgets are clamped to server caps; account ids are opaque strings end
  to end (tests include ids > 2⁵³); errors do not leak internals.
* **Secrets**: none in Git. `.env*` is ignored except `.env.example`. Test passwords exist only for
  disposable databases.
* Open: B1/B2 dependency advisories; Python dependency audit not run.

## 13. Prioritised remaining tasks (details in `ZENCODER_TASKS.md`)

| P | Task |
|---|---|
| P0 | T1 Decide/execute the integration path for stacked PRs #15, #3, #5 and the graph work |
| P0 | T2 Execute the real-webcam checklist; tune recogniser thresholds from findings |
| P0 | T3 Verify the production image (`docker compose up --build`, gateway smoke test, CI `containers` job) |
| P1 | T4 Security documentation for camera mode (SECURITY.md, LIMITATIONS.md) |
| P1 | T5 README / ARCHITECTURE / INTERFACES / CHANGELOG for the graph workspace and gestures; fix the stale PR #3 statement |
| P1 | T6 `react-router-dom` v7 upgrade (B1) |
| P1 | T7 Vite 8 / Vitest 5 upgrades (B2), re-verifying the gesture worker and the asset plugin |
| P2 | T8 Graph stage above the fold at 1440×900 (B3) |
| P2 | T9 ESLint for `apps/web` (B7); ShellCheck + pip-audit in the local gate |
| P2 | T10 Pitch update (optional) |
| — | T11 Deployment to Railway — **only with explicit owner approval** |

## 14. Definition of Done and acceptance criteria

A task is done only when all of the following hold, with output observed, not assumed:

1. All gates pass: `uv run ruff check src tests migrations`, `uv run ruff format --check …`,
   `uv run mypy`, `uv run pytest` (0 skipped, PostgreSQL reachable), `uv run alembic check`,
   `cd apps/web && npx tsc -b && npx vitest run && npx vite build && npx playwright test`
   (from a cold `node_modules/.vite`), `npm run gen:api` produces no diff.
2. No new console errors on any page (the E2E suites assert this) and no CSP violation in the
   production build.
3. UI copy only via `src/lib/i18n.ts`; colours/spacing only via `styles/tokens.css`; colours given
   to Cytoscape go through `toCanvasColor`.
4. Camera invariants hold: no prompt before consent, zero foreign requests, camera released on
   every exit path, gestures cannot write.
5. API schema change ⇒ regenerated and committed `openapi.json` + `api-types.ts`.
6. Docs updated for any user-visible or security-relevant change; no metric quoted that was not
   produced by an executed benchmark run.
7. Tests are never weakened or deleted to get green; any test change states why the behaviour
   changed.
8. Commits on a feature branch; no force-push, no merge to the default branch, no deployment without
   the owner's explicit approval.

## 15. Recommended implementation order

1. Read `/CLAUDE.md`, this file, `ZENCODER_TASKS.md`; run §10 yourself to establish your baseline.
2. **T3** (image build + gateway smoke) — cheapest way to catch production-only defects.
3. **T2** real-webcam checklist (needs a person with a camera) — feeds threshold changes.
4. **T4 + T5** documentation (unblocks review of the PR).
5. **T1** integration of the PR stack with the owner.
6. **T6**, then **T7** dependency upgrades, each on its own branch with the full gate.
7. **T8–T10** polish; **T11** only on approval.
