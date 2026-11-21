# Zencoder task list — Graph Workspace & Gesture Control

Context: [`ZENCODER_HANDOFF.md`](ZENCODER_HANDOFF.md). Baseline: branch `graph-workspace-wip`, all
automated gates green (pytest 190, vitest 99, Playwright 34, build, tsc, mypy, ruff, alembic check,
OpenAPI drift, IaC check). Every task below must end with the full gate (Handoff §14) passing and
its results reported verbatim — including anything that could not be executed.

Legend — **P0** blocks merge/release, **P1** should land before release, **P2** polish.
"Owner" = a decision or action reserved for the repository owner.

---

## T1 (P0) — Integrate the stacked PRs and the graph work · Owner decision

* **Why**: `graph-workspace-wip` contains local merges of PRs #15 (auth), #3 (deep audit /
  hypothesis engine / sealed evaluation) and #5 (pitch), all still **open** against the default
  branch `claude/brave-dirac-c80nwq`. A graph PR opened today would silently carry all three.
* **Depends on**: none. **Blocks**: T11.
* **Affected**: repository branches/PRs only.
* **Requirements**
  1. Present the owner with the two options: (a) merge #15 → #3 → #5 first, then open the graph PR
     (diff = `ff40b72` + `b9943f0` + later commits); (b) one stacked PR, described as such.
  2. Do not merge anything yourself without explicit approval; never force-push shared branches.
  3. If the default branch moved, merge it into a feature branch (no rebase of shared history) and
     re-run the full gate.
* **Test criteria**: PR diff contains only the intended commits; CI green on the PR head.

## T2 (P0) — Real-webcam verification and recogniser tuning

* **Why**: recognition quality on real hands has never been observed (B8).
* **Depends on**: a person with a webcam (Chrome/Edge on desktop; ideally also Firefox and Safari).
* **Affected**: `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` (results log);
  possibly `apps/web/src/features/gestures/recognizer.ts` (`DEFAULT_RECOGNIZER_OPTIONS`),
  `landmarks.ts` (`DEFAULT_POSE_THRESHOLDS`), `oneEuro.ts` parameters.
* **Requirements**
  1. Execute all 20 checklist rows; record browser, OS, camera, pass/fail and observations.
  2. Threshold changes only with evidence from the run (state which row failed and why); keep the
     recogniser pure and deterministic; add a unit test in `recognizer.test.ts` reproducing each
     observed false positive/negative with `syntheticHands.ts`.
  3. Never mark a row passed that was not performed.
* **Test criteria**: checklist log filled; `npx vitest run` and the `gestures` Playwright project pass;
  zero foreign requests in the Network panel during a real session.

## T3 (P0) — Verify the production image and the gateway path

* **Why**: the container image was not built in the handoff environment (no Docker daemon). The
  production build of the gesture worker was verified only behind a Node stand-in for Nginx.
* **Depends on**: Docker with Compose v2; network egress to `storage.googleapis.com` during
  `docker build` (model download, hash-verified).
* **Affected**: `apps/web/Dockerfile`, `apps/web/docker/*`, `docker-compose.yml`,
  `apps/web/playwright.smoke.config.ts`, `.github/workflows/ci.yml` (`containers` job).
* **Requirements**
  1. `docker compose up --build -d --wait`; create a user; run the smoke suite as CI does
     (`NEXORA_SMOKE_USER`/`NEXORA_SMOKE_PASSWORD`, `npx playwright test -c playwright.smoke.config.ts`).
  2. In the running gateway: `curl -sI http://127.0.0.1:8080/vendor/mediapipe/vision_wasm_module_internal.wasm`
     → 200, `application/wasm`, CSP header present; `/vendor/mediapipe/missing` → 404 (not `index.html`).
  3. Manually enable gestures through the gateway once (synthetic or real camera): no CSP violation.
  4. If the build environment cannot reach `storage.googleapis.com`, propose (do not silently add)
     an alternative: vendoring the model via Git LFS or a build arg pointing at an internal mirror,
     keeping the SHA-256 pin.
* **Test criteria**: smoke suite passes; header checks as above; CI `containers` job green.

## T4 (P1) — Security and privacy documentation for camera mode

* **Depends on**: none (T2 results can be added later).
* **Affected**: `SECURITY.md`, `docs/LIMITATIONS.md`, `docs/deployment/railway.md` (CSP section if any).
* **Requirements**: document consent flow, local-only processing, no storage, worker network guard
  (all four channels), CSP directives (`wasm-unsafe-eval`, `worker-src 'self'`, `connect-src 'self'`),
  `Permissions-Policy camera=(self)`, asset pinning and the upgrade procedure for MediaPipe (version
  + three hashes in `scripts/gesture-assets.mjs`), the build-time egress requirement, and the
  limitation that recognition quality is unverified until T2 is done.
* **Test criteria**: every statement traceable to code or an executed test; links resolve
  (`grep` the referenced paths).

## T5 (P1) — Product and architecture documentation

* **Depends on**: T1 decision (so the README describes what will actually merge).
* **Affected**: `README.md`, `docs/ARCHITECTURE.md`, `docs/INTERFACES.md`, `CHANGELOG.md`,
  `docs/design/COMPONENTS.md`, optionally a new screenshot in `docs/assets/screenshots/`.
* **Requirements**
  1. Add the Graph Workspace (`/network`) and camera mode to the feature table and architecture.
  2. Document `GET /api/v1/snapshots/{id}/graph` (graph-view-v1: modes, budgets, `limits`, hashes)
     and `/edge-transactions`.
  3. Fix the stale README warning that calls PR #3 "open, not merged" once T1 is resolved.
  4. Quote only metrics from committed benchmark artifacts.
  5. Screenshots from the production build with synthetic data only.
* **Test criteria**: links resolve; no claim without a source; CHANGELOG has Added/Fixed entries.

## T6 (P1) — Upgrade `react-router-dom` to v7 (advisory B1)

* **Depends on**: none; do on its own branch. Dependabot PR #10 exists (7.18.5; audit asks ≥ 7.18.6).
* **Affected**: `apps/web/package.json`, `package-lock.json`, `src/app/App.tsx`, every
  `useSearchParams`/`Link`/`useNavigate` user (graph workspace URL filters, queue filters, auth
  return-to).
* **Requirements**: follow the v6→v7 upgrade guide (enable future flags first, then bump); keep URL
  formats unchanged (E2E asserts filters survive reload); no behaviour change in auth redirects.
* **Test criteria**: full gate; `npm audit --omit=dev` reports 0 production advisories; the React
  Router warnings (B5) disappear.

## T7 (P1) — Upgrade Vite 8 and Vitest 5 (advisory B2)

* **Depends on**: T6 recommended first (smaller change). Dependabot PRs #11, #13 exist.
* **Affected**: `apps/web/package.json`, `vite.config.ts` (worker format, `optimizeDeps`,
  `test` block), `scripts/gesture-assets.mjs` (Vite plugin hooks `configResolved`/`buildStart`),
  `playwright.config.ts` (dev server command).
* **Requirements**
  1. Keep `optimizeDeps.include: ["@mediapipe/tasks-vision"]` (or the Vite 8 equivalent) — its
     removal reintroduces the mid-session full reload (verify with `rm -rf node_modules/.vite`).
  2. Confirm the worker still builds as an ES module and the asset plugin still fails closed in
     `vite build` and only warns in dev.
* **Test criteria**: full gate from a cold cache; production build behind the gateway CSP (T3
  procedure) passes the `gestures` project; `npm audit` shows no remaining dev-server advisories.

## T8 (P2) — Graph stage visible above the fold

* **Affected**: `apps/web/src/features/graph/GraphWorkspace.tsx`, `src/styles/features.css`,
  `src/styles/layout.css` (tokens only).
* **Requirements**: at 1440×900 the graph stage starts within the first viewport (e.g. collapse the
  filter panel by default when no filter is active, or move filters into a compact toolbar /
  side drawer). Keep: filters open automatically when one is active; mobile graph-first order;
  keyboard/table access; no new hard-coded strings or colours.
* **Test criteria**: new Playwright assertion of the stage's bounding box at 1440×900; existing
  `graph-workspace.spec.ts` (incl. "narrow widths") and `mobile.spec.ts` pass; screenshots
  reviewed in both themes.

## T9 (P2) — Tooling gaps

* ESLint for `apps/web` (mirror `apps/pitch/eslint.config.js`; add to CI and `make lint`). Fix
  findings at the root; do not blanket-disable rules.
* Add ShellCheck and `pip-audit` (or `uv`-based equivalent) to the documented local gate.
* Optional: silence Cytoscape's wheel-sensitivity warning (B4) by removing the custom
  `wheelSensitivity` and routing wheel zoom through `GraphController` — only if the zoom feel is
  verified manually.
* **Test criteria**: new lint step passes in CI; no rule disabled without a comment explaining why.

## T10 (P2, optional) — Pitch update

* **Affected**: `apps/pitch/src/slides/*`, `apps/pitch/public/shots/`.
* **Requirements**: synthetic data only; no unmeasured claims; existing pitch E2E (29) must pass.

## T11 — Deployment · Owner approval required

* **Depends on**: T1, T3 (and ideally T2, T4).
* Use the documented, approval-gated workflow (`docs/deployment/railway.md`,
  `.github/workflows/deploy-railway.yml`); never deploy from an agent session without explicit
  approval; record the deployment in `docs/deployment/railway.md` with what was and was not verified.
