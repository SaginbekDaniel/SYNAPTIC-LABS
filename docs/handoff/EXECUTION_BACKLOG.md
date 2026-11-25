# Execution backlog

Companion to [`MASTER_HANDOFF.md`](MASTER_HANDOFF.md) (read it first: evidence legend, findings `H-nn`,
invariants, decisions). This file is the work queue for an autonomous coding session. Every task is
tied to a finding or a documented gap; none is here to pad the list. Tasks marked **optional** are
real but low-value until someone needs them.

Conventions
* **Priority**: P0 blocks any release/claim, P1 should land before a release, P2 important, P3 optional.
* **Gate** = the full gate in MASTER_HANDOFF §15 (never weaken a test to pass it).
* **Migrations**: take the *next free* revision when you start (today `0005` is head, so `0006`);
  rebase and renumber your own new migration if another task landed first. **Never renumber or edit
  `0001`–`0004`** (production is at `0003`, see H-01). B-001 enforces a single head.
* **Human-gated** tasks need the owner or a person with hardware: B-002 (merge approval), B-005,
  B-030, B-051 (partly), B-055, B-056 (decision D-12). Everything else is autonomous.
* Evaluation work follows the protocol rules in MASTER_HANDOFF §12: no tuning against `sealed-v1`.
* **Status** (one line per task, machine-read by `docs/handoff/probes/progress.py`): `TODO`, `IN_PROGRESS`, `BLOCKED · waiting on …`,
  `IMPLEMENTED` (code written, not yet verified), `VERIFIED` (gate green, not yet pushed/CI-confirmed), `DONE · commit `<sha>` · L-nnnn`
  (acceptance met, CI green, evidence in the ledger). Never mark DONE without the commit and ledger entry.
* **Critical path** (tasks a release cannot ship without; weighted separately by `progress.py`): B-001, B-002, B-003, B-004, B-005, B-010,
  B-011, B-012, B-014, B-030, B-050, B-052, B-055.

## Execution waves and dependency graph

| Wave | Theme | Tasks | Needs before starting |
|---|---|---|---|
| 0 | Integration and ground truth | B-001, B-002*, B-003, B-004, B-005* | — (B-004 after B-003) |
| 1 | Security and observability | B-010, B-011, B-012, B-013, B-014, B-015, B-016, B-017, B-018, B-019 | B-011 after B-001+B-010; B-014 after B-012 |
| 2 | Graph Workspace | B-020, B-021, B-022, B-023, B-024, B-025 | B-021 after B-001; B-023 after B-022; B-025 after B-020 |
| 3 | Gesture control | B-030*, B-031, B-032, B-033 | B-032 after B-031; B-033 after B-030 |
| 4 | Fraud intelligence and evaluation | B-040, B-041, B-042, B-043, B-044, B-045, B-046, B-047, B-048 | B-040, B-041 after B-003; B-048 after B-041 |
| 5 | Platform and product | B-050, B-051*, B-052, B-053, B-054, B-055*, B-056*, B-057 | B-052 after B-002..B-004; B-055 after B-001, B-002, B-005, B-010, B-012, B-050 |

`*` = human-gated. Waves are guidance, not barriers: any task whose listed dependencies are done may
start. **Recommended first autonomous queue:** B-001 → B-010 → B-003 → B-015 → B-012 → B-031 → B-020 →
B-040/B-041. Edges (task → prerequisites): B-003 has none (it ports commits onto the current branch and
does not need the merge decision); B-002→B-001; B-004→B-003; B-011→B-001,B-010; B-014→B-012; B-016→B-015;
B-019→B-011; B-021→B-001; B-023→B-022; B-024→B-020,B-021; B-025→B-020; B-032→B-031; B-033→B-030; B-040→B-003;
B-041→B-003; B-042→B-041; B-043→B-040,B-041; B-044→B-040; B-045→B-040; B-046→B-041; B-048→B-041; B-051→B-005;
B-052→B-002,B-003,B-004; B-054→B-047; B-055→B-001,B-002,B-005,B-010,B-012,B-050; B-056→B-002; B-057→B-055. The graph is acyclic.

Mapping from the earlier `ZENCODER_TASKS.md` (kept for history): T1→B-002, T2→B-030, T3→B-050 (CI
already runs the image build and gateway smoke test; the residual gap is the camera path), T4+T5→B-052,
T6→B-012, T7→B-013, T8→B-022, T9→B-053 (+B-014), T10→B-004, T11→B-055.

---

## Wave 0 — Integration and ground truth

### B-001 · P0 · Single-head migration guard and stepwise-upgrade test
* **Status**: DONE · commit `fdd7465` · L-0005
* **Rationale**: H-01. PR #15 and PR #3 each add a *different* migration with revision `"0003"` on top of
  `0002`; merged separately they create two Alembic heads and `alembic upgrade head` fails at deploy.
  The integration branch renumbered PR #3's to `0004`. Production (per the deployment record) is at
  `0003` = auth, so the only safe fix direction is "hypotheses is 0004".
* **Modules**: `tests/unit/test_migration_chain.py` (new), `.github/workflows/ci.yml`, `migrations/versions/`.
* **Depends on**: none.
* **Implementation**: (1) a unit test using `alembic.script.ScriptDirectory` that asserts exactly one
  head, a linear chain from `0001`, unique revision ids, filename prefix == revision id, and that
  revision `0003` creates `users` while `0004` creates `hypothesis_assessments`; implement the checker as
  a function so a second test feeds it a temp directory with a duplicate `0003` and expects failure.
  (2) an integration test on the disposable database that upgrades `0002 → 0003 → 0004` stepwise
  (simulating production at `0003`) and checks the ORM matches (`alembic check` equivalent).
  (3) add `uv run alembic heads` (one line expected) to the CI "Migrations apply and match ORM" step.
* **Acceptance**: tests pass on the current branch; a branch with a second `0003` fails CI; the stepwise
  upgrade test passes against PostgreSQL 16.
* **Tests**: the two above + `uv run alembic heads`.
* **Expected improvement**: a migration collision is caught on the PR, not at deploy.
* **Risk / rollback**: test-only; revert the commit.

### B-002 · P0 · Reconcile the open PR stack and unmerged branches · human-gated
* **Status**: BLOCKED · waiting on owner approval to merge/close PRs #3/#5/#15 and dispose of stale branches (D-1, D-2)
* **Rationale**: H-01, H-22. `graph-workspace-wip` locally contains PRs #15, #3 and #5 (all still open,
  each based on `ea5ca9c`) plus the graph work, 25 commits ahead of the default branch
  `claude/brave-dirac-c80nwq`. Four more branches hold unmerged work with no PR (see MASTER_HANDOFF §6).
* **Modules**: git and GitHub PRs only.
* **Depends on**: B-001 (so CI protects the result).
* **Implementation**: (1) ask the owner to choose: **A (recommended)** open one PR from
  `graph-workspace-wip` into the default branch and close #3, #5 and #15 as superseded (comment linking the
  merged commits); **B** merge #15, then rebase #3 onto it renumbering its migration to `0004`, then #5,
  then the graph work. (2) Do not merge or close anything without that approval. (3) Branch disposition:
  `sharp-cannon` ⊂ `eloquent-planck` → handled by B-003; `admiring-fermat` ⊂ `great-lovelace` → B-004;
  `peaceful-babbage` (10 ahead / 23 behind, merge-tree conflicts in 11+ files, older "Detection v2" lineage)
  → treat as superseded, propose deletion, never merge. (4) Make sure CI is green on the PR head.
* **Acceptance**: default branch has a single migration head `0004` (or later), CI green on the merge
  commit, #3/#5/#15 closed with explanations, nothing force-pushed.
* **Tests**: CI incl. B-001; `alembic upgrade head` from an empty DB.
* **Expected improvement**: one coherent mainline; the 25 commits stop living on an unreviewed branch.
* **Risk / rollback**: merge is a revert-able commit; do not delete branches until the owner confirms.

### B-003 · P0 · Port the benchmark-arithmetic fixes and regenerate the artifacts
* **Status**: DONE · commit `ef362ac` · L-0007
* **Rationale**: H-08. On the integration branch `benchmark.py::_f1` derives F1 from already-rounded
  precision and recall (holdout v2 stored `0.6855`, exact `146/213 = 0.68545`), and the README states
  `79.4 %` for v2 scenario recall where the committed counts give `73/92 = 79.348 %` → `79.3 %`.
  The Evaluation screen rounds twice. Fixes exist, unmerged, on `origin/claude/eloquent-planck-pwnbd8`
  (`8c7f2ff`, `1867d01`, `d084a97`) and `origin/claude/sharp-cannon-xkrybs` (`65e3894`); `git merge-tree`
  shows conflicts in `Evaluation.tsx`, `bench-v1.json`, `docs/EVALUATION.md`, `tests/unit/test_benchmark.py`.
* **Modules**: `src/nexora/evaluation/benchmark.py`, `scripts/run_benchmark.py`, `scripts/run_sealed_evaluation.py`,
  `src/nexora/api/schemas.py`, `src/nexora/application/evaluation.py`, `apps/web/src/features/evaluation/`,
  `apps/web/openapi.json`, `apps/web/src/lib/api-types.ts`, `benchmarks/results/*.json`, `docs/EVALUATION.md`,
  `docs/evaluation/RESULTS.md`, `README.md`, `tests/unit/test_benchmark.py`, `apps/web/e2e/evaluation.spec.ts`.
* **Depends on**: none (it does not need the merge decision in B-002).
* **Implementation**: on a new branch from `graph-workspace-wip`, cherry-pick the four commits and resolve
  conflicts by keeping the integration branch's structure. **Never hand-merge JSON artifacts**: regenerate
  `bench-v1.json` with `uv run python scripts/run_benchmark.py` on a clean tree, and `dev-evaluation.json` /
  `sealed-evaluation.json` with `scripts/run_sealed_evaluation.py --split dev|sealed` (deterministic except
  latency). Then run `cd apps/web && npm run gen:api`. Diff old vs new artifacts field by field and prove
  every detection count (`tp/fp/fn/tn`, alerts) is unchanged and only derived ratios/latency changed.
  Record the sealed re-generation as **protocol amendment A2** in `docs/evaluation/EXPERIMENT_PROTOCOL.md`
  (metric arithmetic only; detections identical; no new evaluation was run).
* **Acceptance**: F1 equals `2tp/(2tp+fp+fn)` in every summary; README, `docs/EVALUATION.md` and the screen
  show `79.3 %`; the artifact-consistency unit test (recompute every summary from its counts) passes;
  detection counts identical to the pre-change artifacts; full Gate green.
* **Tests**: updated `tests/unit/test_benchmark.py`, `evaluationView.test.ts`, `evaluation.spec.ts`.
* **Expected improvement**: every published ratio recomputes from its counts (CLAUDE.md: no metric quoted
  that an executed run did not produce).
* **Risk / rollback**: regenerated artifacts differ in the 4th decimal and latency; revert the branch.

### B-004 · P1 · Reconcile README and pitch with the verified numbers
* **Status**: VERIFIED
* **Rationale**: H-08, H-22. Jury-facing artifacts diverged: PR #5 (and the integration branch) carry only the
  first pitch (`4e02e9b`); the redesigned pitch is on `admiring-fermat` (`ced8227`, merges cleanly) and the
  README redesign on `great-lovelace` (`e1f597c`, `058a273`; conflicts in `README.md` only). The README still
  says PR #3 is unmerged and its numbers "not applicable".
* **Modules**: `README.md`, `apps/pitch/**`, `docs/assets/screenshots/`.
* **Depends on**: B-003 (numbers must be final first).
* **Implementation**: merge `admiring-fermat`, then `great-lovelace`, resolving the README conflicts by hand;
  update the evaluation section to the regenerated artifacts and delete the stale "PR #3 open" warning;
  add a unit test in `apps/pitch` that every number on the results slide equals the committed artifact (the redesign
  replaced the first pitch's `results.ts` / `sealed-excerpt.json` with `apps/pitch/src/data/bench.ts` and
  `apps/pitch/src/data/bench-excerpt.json`, pinned by `apps/pitch/src/data/bench.test.ts` against `benchmarks/results/bench-v1.json`).
* **Acceptance**: pitch E2E (29+) and unit tests pass; every number in README and pitch traces to a committed
  artifact (the new test covers the pitch; list the README table's sources in the PR).
* **Tests**: `cd apps/pitch && npm run lint && npx tsc -b && npm test && npm run build`, smoke and Playwright.
* **Expected improvement**: one consistent, verifiable story in every artifact a juror may open.
* **Risk / rollback**: documentation and pitch only; revert.

### B-005 · P1 · Verify the live deployment and reconcile the docs · human-gated
* **Status**: BLOCKED · waiting on live Railway workspace/project access
* **Rationale**: H-22. `docs/deployment/railway.md` is a record, not live evidence. In this session the
  connected Railway token authenticated but listed no projects at account level (project likely under a
  workspace), so the live state — deployed commit per service, `alembic_version`, whether the graph workspace
  is live — is **unverified**.
* **Modules**: `docs/deployment/railway.md`.
* **Depends on**: owner provides the workspace/project ids or dashboard access.
* **Implementation**: read-only queries only (deployment status/commit per service, `/health/ready` from the
  private network or the dashboard, `select version_num from alembic_version`). Record results with dates.
  Do not deploy, redeploy, change variables or run migrations.
* **Acceptance**: the deployment record states observed commit SHAs and DB revision, with the date.
* **Tests**: n/a (evidence task).
* **Expected improvement**: removes the assumption that production is at `0003`; unblocks B-051 and B-055.
* **Risk / rollback**: none (read-only).

---

## Wave 1 — Security and observability

### B-010 · P0 · Gate the CSV import endpoint
* **Status**: DONE · commit `bca6f9d` · L-0006
* **Rationale**: H-02. `POST /api/v1/datasets/import` (`src/nexora/api/routes/datasets.py`) accepts any CSV from
  any signed-in user and stores it with `is_synthetic=False` and the free-text note "operator is responsible".
  There is no tenancy, no role, no retention policy and no backup drill; the product claims "synthetic data
  only". The UI does not expose upload, the API does.
* **Modules**: `src/nexora/settings.py`, `src/nexora/api/routes/datasets.py`, `.railway/railway.ts`,
  `.railway/check.ts`, `.env.example`, `docker-compose.yml`, `SECURITY.md`, `tests/integration/test_api.py`,
  `apps/web/openapi.json`, `apps/web/src/lib/api-types.ts`.
* **Depends on**: none. (Owner decision D-4 confirms the default; assume `false` everywhere except local dev.)
* **Implementation**: add `allow_csv_import: bool = False` (`NEXORA_ALLOW_CSV_IMPORT`); when false return
  `403` with code `CSV_IMPORT_DISABLED` before reading the body; keep the route in OpenAPI (regenerate the
  client); set it `false` explicitly in `.railway/railway.ts` and add an invariant to `.railway/check.ts`;
  the two integration tests that call the route (`tests/integration/test_api.py`, `tests/integration/test_investigation_graph.py`) opt in through
  `Settings(allow_csv_import=True)` — the web UI has no upload control, so nothing in the SPA changes.
* **Acceptance**: default settings → 403 and no `datasets`/`transactions` rows created; with the flag on the
  behaviour is unchanged; `npm run check` in `.railway` fails if the flag is true in the deployed definition.
* **Tests**: integration (both modes, asserts no rows), IaC invariant, route-enumeration test still passes.
* **Expected improvement**: the only path by which non-synthetic data could enter the demo is closed by default.
* **Risk / rollback**: tests that import CSV need the opt-in; set the flag true to restore.

### B-011 · P1 · Role model and write permissions
* **Status**: DONE · commit `7b456e3` · L-0018
* **Rationale**: H-09 (audit F-05 still open). Authentication exists; authorization does not: every analyst can
  generate data, run analyses, decide cases and import. No route uses the principal for authorization; case and analysis routes read it only to attribute audit events (`actor` in `src/nexora/api/deps.py`).
* **Modules**: `migrations/versions/` (new revision), `src/nexora/persistence/orm.py` (`User.role`),
  `src/nexora/auth/service.py` (`Principal.role`), `src/nexora/auth/cli.py` (`--role`), `src/nexora/api/deps.py`
  (`require_role`), `src/nexora/api/routes/{cases,analysis,datasets}.py`, `src/nexora/api/schemas.py`,
  `apps/web/src/app/auth.ts`, `apps/web/src/features/{cases,investigation,fraud-lab}/`, `apps/web/src/lib/i18n.ts`,
  `tests/integration/test_auth.py`.
* **Depends on**: B-001, B-010.
* **Implementation**: additive migration `users.role text NOT NULL DEFAULT 'analyst'` with
  `CHECK (role IN ('viewer','analyst','admin'))`. `viewer` = all `GET`s; `analyst` = current behaviour;
  `admin` reserved for operator-only actions (none exposed over HTTP yet). Add a `require_role("analyst")`
  dependency to every state-changing route; extend the route-enumeration test with a per-route minimum-role
  table so a new route cannot be added without declaring one. Expose `role` on `/auth/me`; hide write controls
  for viewers (strings through `i18n.ts`).
* **Acceptance**: a viewer receives `403 FORBIDDEN_ROLE` on every write and can read everything; audit actor is
  unchanged; existing analysts keep working (default `analyst`).
* **Tests**: integration per role × route; unit for the dependency; E2E viewer sees a read-only UI.
* **Expected improvement**: least privilege; demos can be handed to read-only reviewers.
* **Risk / rollback**: additive column; revert the code, the column is harmless.

### B-012 · P1 · Upgrade `react-router-dom` to v7
* **Status**: DONE · commit `9271830` · L-0009
* **Rationale**: H-07. `npm audit` reports advisories on `react-router` 6.0.0–7.17.0 (open redirect via
  backslash in `<Link>`/`useNavigate`, GHSA-wrjc-x8rr-h8h6) — the only advisory that ships to production.
  The fix is a major version (7.18.6 or later; Dependabot PR #10 targets 7.18.5).
* **Modules**: `apps/web/package.json`, `apps/web/package-lock.json`, `apps/web/src/app/App.tsx`, every user of
  `useSearchParams`/`Link`/`useNavigate` (`features/graph`, `features/alerts`, `features/auth`).
* **Depends on**: none.
* **Implementation**: enable the v7 future flags on v6 first (removes the two console warnings), then bump; keep
  URL formats stable (E2E asserts filters survive reload and the sign-in return-to).
* **Acceptance**: `npm audit --omit=dev` reports no react-router advisory; Gate green; no new console errors.
* **Tests**: full Playwright suite, `auth.spec.ts` return-to, graph URL-filter test.
* **Expected improvement**: removes the only production-dependency advisory.
* **Risk / rollback**: routing is central; own branch, revert on regression.

### B-013 · P1 · Upgrade Vite 8 and Vitest 5
* **Status**: TODO
* **Rationale**: H-07. Dev/test-only advisories: vite ≤ 6.4.3 (high), esbuild ≤ 0.24.2, vitest ≤ 4.1.10 and
  tinypool (critical but only when the Vitest UI/API server listens), @vitest/mocker. Fixes are majors
  (Dependabot #11, #13).
* **Modules**: `apps/web/package.json`, `apps/web/vite.config.ts`, `apps/web/scripts/gesture-assets.mjs`,
  `apps/web/playwright.config.ts`.
* **Depends on**: none (after B-012 is the lower-risk order).
* **Implementation**: bump; keep `optimizeDeps.include: ["@mediapipe/tasks-vision"]` (or the Vite 8
  equivalent) — removing it brings back the mid-session full-page reload (verify with `rm -rf node_modules/.vite`);
  confirm the worker still builds as an ES module and the asset plugin still fails closed in `vite build` and
  only warns in dev.
* **Acceptance**: Gate green from a cold cache; `npm audit` shows no remaining dev-server advisories.
* **Tests**: full Playwright incl. `gestures` project, `vite build`, production-bundle run (B-050 procedure).
* **Expected improvement**: closes the dev-tool advisories; keeps tooling current.
* **Risk / rollback**: toolchain change; own branch.

### B-014 · P1 · Dependency-audit gates in CI
* **Status**: TODO
* **Rationale**: H-07. Python dependencies have never been audited (`pip-audit` could not run in this
  environment; `uvx` was refused by the sandbox), and `npm audit` is manual.
* **Modules**: `.github/workflows/ci.yml` (or a new `audit.yml`), `.github/dependabot.yml`.
* **Depends on**: B-012 (so the production gate can pass).
* **Implementation**: CI job that fails on **high/critical advisories in production dependencies**
  (`npm audit --omit=dev --audit-level=high` for `apps/web`, `apps/pitch`, `.railway`; `pip-audit` against
  `uv export --no-dev` for Python) and only reports dev-dependency advisories; also run weekly on a schedule.
* **Acceptance**: job runs in CI and fails when a high production advisory is introduced (prove with a
  throwaway branch pinning a known-vulnerable version).
* **Tests**: the throwaway-branch negative test, recorded in the PR.
* **Expected improvement**: dependency risk becomes visible and enforced.
* **Risk / rollback**: may block on a new advisory; allow-list entries need an expiry date and a reason.

### B-015 · P1 · Structured logging with request-id correlation
* **Status**: DONE · commit `d4192c5` · L-0008
* **Rationale**: H-03. The worker's "JSON" format string is not escaped: `msg:"…relation "transactions"
  does not exist"` is invalid JSON (reproduced), i.e. exactly the error lines break log parsers. The API logs
  plain text and never writes the `request_id` that error envelopes tell users to quote, so a user report
  cannot be traced to a log line.
* **Modules**: `src/nexora/logging.py` (new), `src/nexora/worker/runner.py`, `src/nexora/api/main.py`,
  `Dockerfile`/uvicorn log config, `tests/unit/test_logging.py` (new).
* **Depends on**: none.
* **Implementation**: a `logging.Formatter` that emits `json.dumps` records (ts, level, logger, msg, request_id,
  exc_info as a string); a `contextvars` request id set in the `request_context` middleware; use it in the API
  and worker; have uvicorn use it; log the request id in the 500/503 exception handlers.
* **Acceptance**: every emitted line `json.loads`-parses, including messages with quotes and newlines; a forced
  500 and a forced `OperationalError` each produce a line containing the envelope's `request_id`.
* **Tests**: unit (hostile messages), integration (request id round trip).
* **Expected improvement**: incidents can be traced from the user's `request_id` to the cause.
* **Risk / rollback**: log format change; update any parser before deploying.

### B-016 · P2 · Job events and queue-age signal
* **Status**: TODO
* **Rationale**: H-20. No metrics, error tracking or tracing exist (grep: none). A stuck worker is invisible
  except through `queue` counts in `/health/ready`.
* **Modules**: `src/nexora/worker/runner.py`, `src/nexora/api/main.py` (`/health/ready`), `src/nexora/api/schemas.py`,
  `apps/web/openapi.json`, `docs/deployment/railway.md`.
* **Depends on**: B-015.
* **Implementation**: log one structured event per job (claimed/published/failed with duration, transfers,
  formations, `is_partial`); add `oldest_queued_age_seconds` to the readiness payload. Do **not** add an
  unauthenticated CSP-report endpoint (it would widen the two-route public surface; decision D-9).
* **Acceptance**: events appear for success and failure paths; readiness reports queue age (0 when empty).
* **Tests**: integration with a seeded queued job; worker unit with a failing job.
* **Expected improvement**: a stalled queue is detectable from health and logs.
* **Risk / rollback**: additive fields; revert.

### B-017 · P2 · One database session per request; pool load test
* **Status**: TODO
* **Rationale**: H-10 (design risk, unmeasured). `enforce_authentication` opens its own session and
  `SessionDep` opens another, so each request holds up to two connections from a pool of 5 + 5.
* **Modules**: `src/nexora/api/deps.py`, `src/nexora/settings.py`, `tests/perf/` (new, marker `perf`).
* **Depends on**: none.
* **Implementation**: first **measure**: 50 concurrent authenticated `GET`s against the API, record p95 and any
  `QueuePool limit … timed out`; then reuse one session (resolve the principal in the same dependency chain)
  or document the pool sizing with the measurement. Do not change behaviour without a before/after number.
* **Acceptance**: no pool timeouts at the measured concurrency; p95 recorded before and after.
* **Tests**: perf test (excluded from the default run), existing auth tests unchanged.
* **Expected improvement**: removes a potential latency cliff under concurrent dashboards.
* **Risk / rollback**: touches the auth path — keep `test_every_api_route_rejects_anonymous_requests` green.

### B-018 · P2 · Self-service password change and own-session management
* **Status**: TODO
* **Rationale**: H-21. Passwords can only be changed by the operator CLI; there is no way for an analyst to see
  or end their own sessions.
* **Modules**: `src/nexora/auth/service.py`, `src/nexora/api/routes/auth.py`, `src/nexora/api/schemas.py`,
  `apps/web/src/features/auth/`, `apps/web/src/components/layout/`, `apps/web/src/lib/i18n.ts`, `tests/integration/test_auth.py`.
* **Depends on**: none.
* **Implementation**: `POST /api/v1/auth/password` (current + new; Argon2 work bounded by the existing
  semaphore; revokes the user's *other* sessions; audit event), `GET /api/v1/auth/sessions`,
  `DELETE`/`POST` to end one. CSRF and origin checks as for every write; no password in logs.
* **Acceptance**: wrong current password → generic failure and counts toward throttling; success revokes other
  sessions and keeps the current one; every action audited.
* **Tests**: integration (throttle, revocation, audit), E2E account menu.
* **Expected improvement**: closes a known operational gap without an external IdP.
* **Risk / rollback**: new write endpoints on the auth surface; own review for CSRF/throttle parity.

### B-019 · P2 · Dataset ownership and isolation · requires decision D-3
* **Status**: BLOCKED · waiting on decision D-3 (data-isolation model)
* **Rationale**: H-09. Every signed-in user can read every dataset, alert, transaction and case.
* **Modules**: `migrations/versions/` (new), `src/nexora/persistence/orm.py`, `src/nexora/application/queries.py`,
  all dataset-/snapshot-/alert-/case-scoped routes, `tests/integration/`.
* **Depends on**: B-011.
* **Implementation**: after the owner picks the model (D-3: per-user private datasets, shared-by-default with
  owner-only writes, or explicit membership), add `datasets.owner_user_id` (nullable for existing rows =
  shared) and filter every query by access. Return **404** (not 403) for datasets a user cannot see, so
  existence is not leaked. Cover every route whose path carries `dataset_id`, `snapshot_id`, `alert_id`,
  `case_id` by enumerating OpenAPI, as the anonymous-access test does.
* **Acceptance**: a second user receives 404 on every scoped route for the first user's private dataset;
  list endpoints omit it; admin sees all.
* **Tests**: parametrised cross-user test over all scoped routes (generated from OpenAPI).
* **Expected improvement**: real data isolation, the precondition for any multi-analyst use.
* **Risk / rollback**: query-path change across the API; ship behind the decision, test exhaustively.

---

## Wave 2 — Graph Workspace

### B-020 · P1 · Layout off the main thread, and cached
* **Status**: DONE · commit `0340f1a` · L-0011
* **Rationale**: H-04. Cytoscape `cose` runs synchronously on the main thread: headless probe 50 nodes 109 ms,
  100 → 355 ms, 200 → 1,150 ms, 300 → 2,791 ms (`docs/handoff/probes/cose_layout.mjs`). The workspace requests
  200 nodes and caps merged expansions at 400 (`MAX_WORKSPACE_NODES`); every filter change or expansion rebuilds
  the instance and re-runs the layout. The same thread runs the gesture frame loop and keyboard handling.
* **Modules**: `apps/web/src/components/graph/GraphCanvas.tsx`, `apps/web/src/features/graph/graphModel.ts`,
  a new layout worker `apps/web/src/components/graph/layoutWorker.ts` (new), `apps/web/e2e/graph-workspace.spec.ts`.
* **Depends on**: none.
* **Implementation**: compute positions in a module worker (headless Cytoscape or a faster force layout —
  choose by measuring with the probe) and apply them with a `preset` layout; cache positions by
  `(snapshot id, view key, element-set hash)` so the deterministic seeded layout is not recomputed; keep
  `randomize: false` and the seeding so the "same snapshot, same picture" test still holds; show the existing
  loading state while the worker runs; terminate the worker on unmount.
* **Acceptance**: no long task over 200 ms during layout at 300 nodes (Playwright `PerformanceObserver`
  `longtask`), the layout is identical to today's for the same input (or the difference is documented and the
  determinism test updated deliberately), gestures keep tracking while a layout runs.
* **Tests**: E2E long-task assertion, determinism test, unit for the cache key.
* **Expected improvement**: removes 1–3 s UI freezes at 200–300 nodes.
* **Risk / rollback**: layout is core UX; keep the synchronous path behind a flag until verified.

### B-021 · P2 · Push graph ranking and expansion into SQL
* **Status**: TODO
* **Rationale**: H-06. `bfs_neighborhood` runs one aggregate query per expanded node (depth 2 = one per
  depth-1 neighbour: 204 ms vs 11 ms for depth 1 on only 5k rows) and truncates *after* fetching: a hub with
  20,000 peers returns 40,000 aggregate rows to Python to keep 398 edges. `_formations()` loads every formation
  of the snapshot and sorts in Python on each call, including local mode (code reading; unmeasured).
* **Modules**: `src/nexora/application/graph_view.py`, `migrations/versions/` (new, GIN index on the JSONB
  columns `formations.member_ids` / `exit_ids`), `tests/integration/test_investigation_graph.py`.
* **Depends on**: B-001.
* **Implementation**: batch each BFS level (`= ANY(:frontier)`), apply top-K by amount in SQL, `ORDER BY`/`LIMIT`
  formations in SQL for overview and, for local mode, a JSONB containment test (`member_ids ?| array[...]`, which a default GIN index supports) plus
  `subject_account_id` and `exit_ids`, because the Python helper `_accounts_of` counts all three. **Preserve ordering
  semantics exactly** (heaviest edges first, the existing tiebreaks).
* **Acceptance**: `docs/handoff/probes/scale_graph.py` improves by at least 3× on depth 2 and the hub
  expansion no longer returns tens of thousands of rows; `test_investigation_graph.py` passes unchanged; a
  property test shows old and new implementations return identical views on random graphs.
* **Tests**: existing 7 integration tests + the equivalence property test + probe before/after in the PR.
* **Expected improvement**: bounded *work*, not only bounded response size.
* **Risk / rollback**: query rewrite; keep the old code path in the test as the oracle.

### B-022 · P2 · Graph stage above the fold at 1440 × 900
* **Status**: TODO
* **Rationale**: H-23. The filter panel pushes the stage to y ≈ 580 of 900 (screenshot taken this project).
* **Modules**: `apps/web/src/features/graph/GraphWorkspace.tsx`, `apps/web/src/styles/features.css`,
  `apps/web/src/styles/layout.css`, `apps/web/e2e/graph-workspace.spec.ts`.
* **Depends on**: none.
* **Implementation**: collapse filters by default when none is active (they already open automatically when one
  is), or move them to a compact toolbar; keep graph-first order on phones; strings via `i18n.ts`, spacing via tokens.
* **Acceptance**: the stage's top edge is within the first viewport at 1440 × 900; existing narrow-width and
  mobile tests pass; both themes reviewed.
* **Tests**: new bounding-box assertion in `graph-workspace.spec.ts`.
* **Expected improvement**: the graph is visible on arrival.
* **Risk / rollback**: layout CSS; revert.

### B-023 · P2 · Automated accessibility audit of the workspace
* **Status**: TODO
* **Rationale**: the graph has keyboard navigation, a live region and a table fallback, but accessibility is
  asserted only in places, never scanned. Colour contrast of band colours on the stage is unmeasured.
* **Modules**: `apps/web/package.json` (dev dependency), `apps/web/e2e/a11y.spec.ts` (new),
  `docs/research/LICENSE_MATRIX.md` (record the licence, ADR-013), `apps/web/src/styles/tokens.css`.
* **Depends on**: B-022.
* **Implementation**: add an axe-based Playwright check for `/network`, `/alerts`, an investigation and the
  gesture consent dialog, in both themes and at 390 px; fix `serious`/`critical` findings at their root (tokens,
  labels); write the keyboard map into the UI help.
* **Acceptance**: zero serious/critical violations on the audited pages; remaining items listed with reasons.
* **Tests**: the new spec runs in the Playwright suite.
* **Expected improvement**: measurable accessibility baseline.
* **Risk / rollback**: verify the dependency licence first; remove the spec if it cannot be adopted.

### B-024 · P3 · optional · Path between two accounts
* **Status**: TODO
* **Rationale**: an analyst question the workspace cannot answer today ("how is A connected to B?").
  Do not start without analyst feedback; it is productivity, not correctness.
* **Modules**: `src/nexora/application/graph_view.py`, `src/nexora/api/routes/analysis.py`, `apps/web/src/features/graph/`.
* **Depends on**: B-020, B-021.
* **Implementation**: bounded shortest-path over the same eligible aggregates (depth ≤ 4, edge budget), returned
  in the graph-view shape and highlighted; stored risk only, nothing scored.
* **Acceptance**: path edges recompute from `edge-transactions`; budgets honoured; ids > 2⁵³ round-trip.
* **Tests**: integration (path exists/absent/over budget), E2E.
* **Expected improvement**: faster link analysis.
* **Risk / rollback**: new read endpoint; revert.

### B-025 · P2 · Keep the drawn graph during relayout; budget the whole main-thread path
* **Status**: TODO
* **Rationale**: follow-up to B-020 (L-0016 observations, confirmed in the code in L-0017). (1) The build effect in
  `GraphCanvas.tsx` destroys the drawn instance in its cleanup as soon as the element set changes, so every filter
  change or expansion shows an empty stage until the worker returns — up to ~2.6 s at 300 accounts (L-0011). (2) The
  headless sizing probe and `layoutDimensions` run synchronously *before* `LAYOUT_MARK_START`, outside the window the
  E2E long-task assertion measures; L-0011 recorded main-thread tasks of 67–229 ms around it, i.e. up to 29 ms over
  B-020's 200 ms budget, unattributed.
* **Modules**: `apps/web/src/components/graph/GraphCanvas.tsx`, `apps/web/src/components/graph/layoutClient.ts`,
  `apps/web/src/components/graph/controller.ts`, `apps/web/src/lib/i18n.ts`, `apps/web/e2e/graph-workspace.spec.ts`.
* **Depends on**: B-020.
* **Implementation**: measure first — mark the probe, worker, mount and first-paint phases at 100/200/300/400
  accounts on the production bundle and attribute each long task (Cytoscape construction, React, application code).
  Then keep the previous instance mounted but inert while a relayout runs (marked stale: `aria-busy`, controller
  and gestures detached so nothing acts on elements about to change, status announced through `i18n.ts`), swap
  atomically on the new positions, destroy the old instance after the swap; a superseded result is dropped (already
  `LayoutCancelled`); unmount still cancels the worker. Move or split the sizing probe only if it is the measured cost.
* **Acceptance**: during a relayout the stage is never empty and the old drawing accepts no selection/expansion;
  exactly one drawn instance exists after the swap (no leaked Cytoscape instances over 20 relayouts); no long task
  over 200 ms anywhere between the triggering change and the interactive new graph at 300 accounts (production
  bundle, Chromium); gestures keep tracking; existing determinism and cache tests unchanged.
* **Tests**: E2E long-task assertion over the whole path; E2E stale-stage behaviour (old drawing visible, inert,
  `aria-busy`); unit for instance lifecycle (swap, supersede, unmount).
* **Expected improvement**: no blank stage on relayout; the 200 ms budget holds end to end instead of only inside
  the worker window.
* **Risk / rollback**: graph lifecycle is core UX and gesture-coupled; keep the change inside `GraphCanvas`, revert
  restores B-020's behaviour.

---

## Wave 3 — Gesture control

### B-030 · P0 · Real-webcam verification and sign-off · human-gated
* **Status**: BLOCKED · waiting on a person with a physical webcam
* **Rationale**: H-17/B8. Every gesture test uses Chromium's synthetic camera (no hand) or a scripted landmark
  worker. Recognition on real hands has never been observed.
* **Modules**: `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` (results log).
* **Depends on**: a person with a webcam (Chrome/Edge desktop; Firefox/Safari if available).
* **Implementation**: execute all 20 checklist rows against a production-like build; record browser, OS, camera,
  result, observations. Do not mark a row passed that was not performed.
* **Acceptance**: the results log is filled; defects found are filed as backlog items with traces.
* **Tests**: the manual checklist; zero foreign requests in the Network panel.
* **Expected improvement**: the first real evidence about recognition quality.
* **Risk / rollback**: none.

### B-031 · P1 · Load the model before asking for the camera
* **Status**: DONE · commit `d0cb21e` · L-0010
* **Rationale**: H-05. `GestureSession.start()` starts the camera, then loads the model: the camera light is on
  while ~22.8 MB of WASM and model (7.8 MB model, 14.6 MB WASM, 0.33 MB loader, uncompressed) downloads and
  initialises, up to the 30 s timeout. The sequence observed in the E2E trace was starting → loading →
  calibrating with the camera live from `loading`.
* **Modules**: `apps/web/src/features/gestures/gestureSession.ts`, `landmarkEngine.ts`, `GestureControl.tsx`,
  `apps/web/src/lib/i18n.ts`, `apps/web/e2e/gestures.spec.ts`, a unit test for the session ordering (new).
* **Depends on**: none.
* **Implementation**: start the engine first (status "loading model"), call `getUserMedia` only after the engine
  reports ready, keeping the consent-first flow and every existing exit path; handle cancel during either phase
  (generation counter already exists).
* **Acceptance**: while the status is "loading" the number of live camera tracks is 0 and `getUserMedia` has not
  been called; the E2E proves it by delaying `/vendor/mediapipe/*` with `page.route`.
* **Tests**: unit (ordering with fake camera/engine), E2E (delayed assets), existing gesture tests unchanged.
* **Expected improvement**: the camera is on only when recognition can actually run.
* **Risk / rollback**: lifecycle code; keep the existing stop-path tests green.

### B-032 · P2 · Browser support policy and capability detection
* **Status**: TODO
* **Rationale**: H-17 (hypothetical, untested). Only Chromium is exercised. MediaPipe inside a worker needs
  module workers, `OffscreenCanvas` and WebGL2; `createImageBitmap` resize options are not uniformly supported.
* **Modules**: `apps/web/src/features/gestures/GestureControl.tsx` (`useGesturesSupported`),
  `landmarkEngine.ts`, `apps/web/playwright.config.ts`, `docs/implementation/GRAPH_GESTURE_VERIFICATION.md`.
* **Depends on**: B-031.
* **Implementation**: detect the needed capabilities before offering the toggle and explain when unavailable;
  add Firefox and WebKit Playwright projects for the lifecycle/fallback tests where the engine allows fake
  media; publish a support matrix containing only results actually observed.
* **Acceptance**: on a browser lacking a capability the toggle explains why and the graph stays fully usable;
  the matrix lists observed results.
* **Tests**: new projects/specs; unit for capability detection.
* **Expected improvement**: no silent failure outside Chromium.
* **Risk / rollback**: extra CI time; the new projects may be non-blocking until stable.

### B-033 · P2 · Recorded-landmark fixtures and threshold tuning
* **Status**: TODO
* **Rationale**: B8. Recogniser thresholds are untuned on real hands.
* **Modules**: `apps/web/src/features/gestures/recognizer.ts`, `landmarks.ts`, `oneEuro.ts`,
  `apps/web/src/features/gestures/fixtures/` (new), `recognizer.test.ts`.
* **Depends on**: B-030.
* **Implementation**: a developer-only way to export landmark traces (numbers only, no video) from consenting
  developers' own sessions; replay them in unit tests; change a threshold only with a trace showing why;
  measure idle false-trigger rate per minute.
* **Acceptance**: fixtures from varied lighting/hands; measured false triggers per idle minute before/after.
* **Tests**: replay tests over the fixtures.
* **Expected improvement**: evidence-based recognition stability.
* **Risk / rollback**: never commit traces from people who did not agree.

---

## Wave 4 — Fraud intelligence and evaluation

### B-040 · P0 (before any detector tuning) · Create `sealed-v2` and lock its protocol
* **Status**: DONE · commit `0dd9cd7` · L-0015
* **Rationale**: H-14. `sealed-v1` was evaluated once and has been **consumed**: any further detector or policy
  change judged on it is selection on the test set. The `bench-v1` holdout was already exposed.
* **Modules**: `src/nexora/evaluation/sealed_generator.py` (or a new `sealed_generator_v2.py`),
  `scripts/run_sealed_evaluation.py`, `docs/evaluation/EXPERIMENT_PROTOCOL.md`, `benchmarks/results/`,
  `tests/unit/` (generator completeness and label-blindness tests).
* **Depends on**: B-003.
* **Implementation**: new generator revision with changed parameter ranges and at least some new families,
  disjoint seeds (v1 used 9000–9059), label-blind boundaries (audit L-01), complete truth lists (F-08); write
  and **commit the protocol before any candidate is run**; one run; record code, generator, harness and
  config hashes in the artifact.
* **Acceptance**: the protocol commit precedes the artifact commit in `git log`; generator tests pass; artifact
  reproduces field for field on re-run (except latency).
* **Tests**: generator unit tests mirroring those of `sealed-v1`; reproducibility check.
* **Expected improvement**: a clean held-out set for every later claim.
* **Risk / rollback**: none for the product; the cost is discipline — never peek before the protocol is locked.

### B-041 · P1 · Entity-level, ranking and calibration metrics
* **Status**: DONE · commit `85f8b5e` · L-0013
* **Rationale**: H-12. The harness reports network-level precision/recall/P@K only (grep for account-level,
  AUC, calibration, Brier: none). Priority is uncalibrated by design (ADR-005) but nothing measures how bands
  relate to the planted fraction, and classical account-level baselines cannot be compared fairly.
* **Modules**: `src/nexora/evaluation/benchmark.py`, `scripts/run_sealed_evaluation.py`,
  `src/nexora/api/schemas.py`, `docs/evaluation/RESULTS.md`, `tests/unit/test_benchmark.py`.
* **Depends on**: B-003.
* **Implementation**: add (a) account-level recall/precision against the complete truth lists, (b) a
  precision–recall curve and area over priority, (c) reliability by band with Wilson intervals (planted
  fraction per band), (d) the same for the baselines B0/B1/B3, with bootstrap intervals; label everything
  synthetic; add numerators/denominators so every ratio recomputes from counts.
* **Acceptance**: new fields in the artifact; hand-computed tiny fixtures pin each metric; no README claim is
  added until an executed run produces it.
* **Tests**: unit with fixtures, artifact-consistency test.
* **Expected improvement**: defensible, entity-level comparison with simple baselines.
* **Risk / rollback**: additive metrics.

### B-042 · P1 · Group related alerts
* **Status**: TODO
* **Rationale**: H-11. A funnel and a fan-out on the same hub open separate alerts (fingerprints are per
  pattern kind); sealed candidate has 1.232 alerts per flagged network (baseline 1.667).
* **Modules**: `src/nexora/application/queries.py`, `src/nexora/api/routes/alerts.py`, `src/nexora/api/schemas.py`,
  `apps/web/src/features/alerts/`, `apps/web/src/lib/i18n.ts`, `apps/web/e2e/redesign.spec.ts`.
* **Depends on**: B-041 (to measure).
* **Implementation**: group at **query time** (union-find over shared accounts between alerts of one snapshot),
  expose `group_id` and the group's strongest band; show "related alerts"; never merge or alter assessments,
  never drop an alert.
* **Acceptance**: grouping is deterministic and independent of row order (metamorphic test); alert counts are
  unchanged; the sealed alerts-per-network figure is reported before/after.
* **Tests**: unit (union-find), integration (queue payload), metamorphic, E2E.
* **Expected improvement**: fewer repeated reviews of one hub.
* **Risk / rollback**: read-path only; revert.

### B-043 · P2 · Detect slow accumulation without raising false positives
* **Status**: TODO
* **Rationale**: H-16, audit F-06. Recurring-mule collection is flagged 1/8 and slow collection 9/12 on sealed
  because deposits held longer than `max_hop_lag_days: 7` contradict the temporal flow.
* **Modules**: `src/nexora/analytics/temporal/flow.py` (new flow version), `configs/detectors.yaml`,
  `configs/risk_policy.yaml`, `tests/unit/test_temporal_flow.py`.
* **Depends on**: B-040, B-041.
* **Implementation**: pre-register in the B-040 protocol a success rule (SX4/SX5 recall up; legitimate-family
  false positives not up beyond the interval) **before** running; implement an accumulation-window variant as a
  new config version (new snapshot identity); evaluate on dev and `sealed-v2` only.
* **Acceptance**: the pre-registered rule is met, or the variant is rejected and recorded as a negative result.
* **Tests**: unit scenarios for held-then-forwarded flows; harness run.
* **Expected improvement**: closes the largest documented recall gap, if the data support it.
* **Risk / rollback**: config-versioned; old behaviour reproducible.

### B-044 · P2 · Competing-explanation engine for chains and cycles
* **Status**: TODO
* **Rationale**: H-15. The hypothesis engine covers only `funnel` and `fan_out` (`configs/detectors.yaml:
  hypotheses.kinds`); chains and loops have no benign-explanation test.
* **Modules**: `src/nexora/analytics/hypotheses/engine.py`, `configs/detectors.yaml`, `docs/architecture/HYPOTHESIS_ENGINE.md`,
  `tests/unit/test_hypotheses.py`.
* **Depends on**: B-040.
* **Implementation**: define the legitimate explanations for pass-through/loop shapes (e.g. payment routing,
  reimbursement chains), each with an independent observation group and the data that would decide it; keep
  "two independent groups for a benign verdict"; pre-register and evaluate on `sealed-v2`.
* **Acceptance**: pre-registered success rule met, or rejected and recorded.
* **Tests**: unit scenarios with counterexamples; harness.
* **Expected improvement**: fewer legitimate chain alerts, explained.
* **Risk / rollback**: config flag `hypotheses.kinds`.

### B-045 · P2 · Adversarial evasion suite
* **Status**: TODO
* **Rationale**: H-14/H-16, audit F-02/F-07. Known evasions (token repayments ≥ 10 % in fan-out, amounts below
  materiality floors, timing beyond the lag, synthetic recurrence/active span to win the benign verdict) are
  documented but not measured as a suite.
* **Modules**: `src/nexora/evaluation/` (new generator families), `docs/evaluation/`, `tests/unit/`.
* **Depends on**: B-040.
* **Implementation**: generate each evasion at several strengths; report per-family detection degradation as a
  curve; **do not tune on the suite** — any fix needs a fresh unseen set.
* **Acceptance**: report committed with the artifact; limitations updated with measured numbers.
* **Tests**: generator unit tests.
* **Expected improvement**: robustness is quantified instead of asserted.
* **Risk / rollback**: evaluation-only.

### B-046 · P2 · Resolve `NETWORK_CONTEXT`
* **Status**: TODO
* **Rationale**: H-13. The family carries weight 0.15 in `risk-policy-v3` but no code ever produces a
  `NETWORK_CONTEXT` signal, so the practical priority ceiling is 85 and `critical` (≥ 80 and three supported
  families) needs 94 % of that ceiling.
* **Modules**: `configs/risk_policy.yaml`, `src/nexora/analytics/risk.py`, `docs/ADR/0001-decisions.md`,
  a new detector under `src/nexora/analytics/` if (a) is chosen.
* **Depends on**: B-041.
* **Implementation**: first measure the band distribution in the committed artifacts (how many `critical`),
  then decide: (a) build a bridge/coordinator detector and evaluate it, or (b) remove the family and rescale
  weights/bands as `risk-policy-v4`; record the decision as ADR-021.
* **Acceptance**: ADR written with the measurement; policy and docs consistent; sealed-v2 run if (b) changes bands.
* **Tests**: policy unit tests for the new bands.
* **Expected improvement**: a priority scale whose maximum is reachable.
* **Risk / rollback**: policy is versioned; old snapshots keep their policy hash.

### B-047 · P2 · Scale regression tests
* **Status**: TODO
* **Rationale**: H-18/N-1. Measured (probe): the pure pipeline takes 22.5 s and 381 MiB peak RSS at the documented
  200,000-row cap (worker limit 1,024 MiB), 10.4 s / 208 MiB at 100k, 5.9 s / 120 MiB at 50k. Not measured: ORM
  load of 200k rows and the publish transaction. No committed test exceeds ~1k transfers per dataset.
* **Modules**: `tests/perf/` (new, marker `perf`), `.github/workflows/` (scheduled/manual job),
  `docs/handoff/probes/`.
* **Depends on**: none.
* **Implementation**: promote the probes to `perf`-marked tests with budgets set at roughly 2× today's
  numbers; add `load_transfers` and `publish` timings against a real database; run nightly or on demand, not
  in the default gate.
* **Acceptance**: budgets recorded; the scheduled job passes and fails when a budget is exceeded (prove once).
* **Tests**: the perf tests themselves.
* **Expected improvement**: a performance regression is caught before users feel it.
* **Risk / rollback**: CI-minutes cost; keep it non-blocking.

### B-048 · P3 · Account-level positives: count only accounts present in the data
* **Status**: BLOCKED · waiting on owner decision on fixing the frozen generators (H-25)
* **Rationale**: H-25. Truth lists of the frozen development generator and of `sealed-gen-v1` name accounts that
  never transact; account-level recall counts them as unreachable positives (`bench-v1` holdout: 1 of 735, effect
  ≤ 0.0013). The generators and artifacts are frozen, so the correction belongs in the metric definition.
* **Modules**: `src/nexora/evaluation/entity_metrics.py`, `scripts/run_benchmark.py`,
  `docs/evaluation/EXPERIMENT_PROTOCOL.md` (amendment), `tests/unit/test_entity_metrics.py`,
  `tests/unit/test_truth_account_presence.py`, `benchmarks/results/`.
* **Depends on**: B-041.
* **Implementation**: record a protocol amendment (A3, metric definition only) *before* regenerating; then count as
  positives (and as labelled legitimate) only truth accounts that occur in the dataset's rows, report the excluded
  count next to the denominator, regenerate `bench-v1.json` and the dev artifact. `sealed-evaluation.json` is not
  re-run (consumed); sealed-v2 has no absent accounts, so its numbers cannot change.
* **Acceptance**: artifacts regenerated with only account-level positives/recall changing, by exactly the absent
  counts in `test_truth_account_presence.py`; every other count identical; amendment committed first.
* **Tests**: fixture with an absent truth account in `test_entity_metrics.py`; artifact-consistency test.
* **Expected improvement**: account recall that no method is structurally prevented from reaching.
* **Risk / rollback**: touches published artifacts; owner may prefer to leave them and keep H-25 as a documented
  limitation — decide before starting. Rollback: revert the commit and the artifacts.

---

## Wave 5 — Platform and product

### B-050 · P1 · Exercise the camera path through the real gateway image in CI
* **Status**: TODO
* **Rationale**: H-19. CI builds both images and runs a smoke test through the gateway, which loads `/network`
  and asserts no console/CSP errors — but never starts the camera or fetches `/vendor/mediapipe/*`. The
  production-CSP gesture run in this project used a Node stand-in
  (`docs/handoff/probes/gateway_sim.mjs`), not Nginx.
* **Modules**: `apps/web/smoke/` (new gesture smoke), `apps/web/playwright.smoke.config.ts`,
  `.github/workflows/ci.yml` (`containers` job), `apps/web/docker/default.conf.template`.
* **Depends on**: none.
* **Implementation**: add a smoke test that, through the gateway with fake-camera flags, asserts the wasm and
  model return 200 with the right content type and the CSP header, starts the camera, sees no CSP violation and
  no foreign request; add a negative check that removing `wasm-unsafe-eval` makes it fail.
* **Acceptance**: the CI `containers` job runs it green; the negative check fails as expected (recorded).
* **Tests**: the new smoke spec.
* **Expected improvement**: the real production path of the camera feature is covered.
* **Risk / rollback**: CI time; the spec can be marked non-blocking while stabilising.

### B-051 · P1 · Backup/restore drill and retention policy · partly human-gated
* **Status**: BLOCKED · waiting on B-005 and decision D-5 (retention)
* **Rationale**: H-20. No backup/restore drill, retention policy or key-management review exists
  (`SECURITY.md`, `docs/deployment/railway.md` say so).
* **Modules**: `docs/deployment/railway.md`, `docs/runbooks/restore.md` (new), `SECURITY.md`.
* **Depends on**: B-005 (needs live access and the owner enabling scheduled backups).
* **Implementation**: `pg_dump` → restore into a scratch database → verify `alembic_version`, row counts, and
  that the API starts and `/health/ready` is `ok`; record measured restore time; propose retention for
  datasets, audit events (currently unbounded), sessions (7 days) and login attempts (7 days) — the owner decides (D-5).
* **Acceptance**: a runbook with a measured restore time and a dated drill record.
* **Tests**: the drill itself (scripted where possible).
* **Expected improvement**: recovery is known to work.
* **Risk / rollback**: never restore over a live database.

### B-052 · P1 · Documentation consolidation
* **Status**: TODO
* **Rationale**: H-08, H-22. README, `docs/ARCHITECTURE.md`, `docs/INTERFACES.md`, `SECURITY.md`,
  `docs/LIMITATIONS.md` and `CHANGELOG.md` do not describe the graph workspace, graph-view-v1, the camera
  mode or its privacy model; the README carries a stale "PR #3 open" warning.
* **Modules**: those files plus `docs/TEST_REPORT.md`, `scripts/check_docs_links.py` (new), `.github/workflows/ci.yml`.
* **Depends on**: B-002, B-003, B-004.
* **Implementation**: document the workspace, both graph endpoints and their budgets, the gesture pipeline,
  consent flow, worker network guard, CSP/Permissions-Policy, asset pinning and the MediaPipe upgrade
  procedure (version + three hashes in `apps/web/scripts/gesture-assets.mjs`), and the build-time egress requirement;
  add a link checker (paths in backticks and markdown links) to CI.
* **Acceptance**: link checker passes in CI; every claim traces to code or an executed test; metrics only from artifacts.
* **Tests**: the link checker.
* **Expected improvement**: docs match the product.
* **Risk / rollback**: documentation only.

### B-053 · P2 · ESLint for `apps/web`
* **Status**: TODO
* **Rationale**: H-24. `apps/pitch` lints; `apps/web` only type-checks.
* **Modules**: `apps/web/eslint.config.js` (new), `apps/web/package.json`, `.github/workflows/ci.yml`, `Makefile`.
* **Depends on**: none.
* **Implementation**: mirror `apps/pitch/eslint.config.js`, fix findings at the root (no blanket disables), add
  to `make lint` and CI.
* **Acceptance**: lint passes in CI; any disabled rule has a comment explaining why.
* **Tests**: CI.
* **Expected improvement**: a class of defects is caught before review.
* **Risk / rollback**: may surface many findings; fix in one dedicated commit.

### B-054 · P3 · optional · Near-real-time ingestion: decide with numbers
* **Status**: BLOCKED · waiting on decision D-10 (latency target) and B-047
* **Rationale**: H-18. The system is batch and full-recompute by design (ADR-011); a full recompute costs
  22.5 s / 381 MiB at 200k transfers. Whether incremental analysis is worth building depends on a stated latency need.
* **Modules**: `docs/ADR/0001-decisions.md` (ADR-022), `docs/handoff/probes/`.
* **Depends on**: B-047.
* **Implementation**: write an ADR with the latency requirement the owner states, a measured comparison of
  re-analysing only the connected components touched by new transfers vs full recompute, and a go/no-go.
  Build nothing until the requirement and measurement justify it.
* **Acceptance**: ADR with measurements and a decision.
* **Tests**: the measurement script.
* **Expected improvement**: avoids building (or skipping) a streaming system on a guess.
* **Risk / rollback**: documentation only.

### B-055 · P1 · Deploy the integrated line · owner approval required
* **Status**: BLOCKED · waiting on owner deployment approval; prerequisites B-002, B-005, B-050
* **Rationale**: the live demo predates the graph workspace and gestures (per the deployment record; see B-005).
* **Modules**: `docs/deployment/railway.md`, `.github/workflows/deploy-railway.yml`.
* **Depends on**: B-001, B-002, B-005, B-010, B-012, B-050.
* **Implementation**: only with explicit owner approval, via the documented approval-gated workflow; confirm the
  migration plan (`0003 → head` applies only the new revisions), keep `NEXORA_ALLOW_CSV_IMPORT=false`, run the
  deployed smoke test, record what was and was not verified.
* **Acceptance**: dated deployment record with observed commit SHAs and `/health/ready` revision.
* **Tests**: deployed smoke test (`playwright.smoke.config.ts`).
* **Expected improvement**: the verified work is actually live.
* **Risk / rollback**: documented rollback (Redeploy previous deployment; migrations are additive).

### B-057 · P2 · Results slide and README headline on the shipped configuration
* **Status**: TODO
* **Rationale**: H-27. The pitch's results slide and the README's first table show configuration v2 on the exposed
  `bench-v1` holdout (now labelled as such, B-004). That matches the live demo, which still runs v2 (`f29ae56`), but this
  branch ships v3, whose stronger evidence is the pre-registered `sealed-v2` run. Once v3 is deployed the pitch should lead
  with what is deployed.
* **Modules**: `apps/pitch/src/data/bench.ts`, `apps/pitch/scripts/extract-bench.mjs`, `apps/pitch/src/slides/Slide6.tsx`, `README.md`,
  `tests/unit/test_readme_numbers.py`.
* **Depends on**: B-055.
* **Implementation**: extract the `sealed-v2` candidate and `B1_rules` figures with a script (never by hand), keep the
  per-family misses and the limits from `docs/evaluation/RESULTS.md`, keep the "synthetic, not bank data" guard; do not
  run anything new on `sealed-v2` (protocol "Use after the run").
* **Acceptance**: pitch unit test pins every figure to `sealed-v2-evaluation.json`; README traceability test updated; pitch
  E2E green; desktop screenshot checked.
* **Tests**: `cd apps/pitch && npm test && npx playwright test`; `uv run pytest tests/unit/test_readme_numbers.py`.
* **Expected improvement**: the deck shows the product that is live, with its best evidence.
* **Risk / rollback**: pitch and README only; revert.

### B-056 · P1 · Integrate the transfer-protection demo (`feat/transfer-protection`) · requires decision D-12
* **Status**: BLOCKED · waiting on decision D-12 (authentication model for the client-facing transfer check)
* **Rationale**: H-26. A collaborator's branch `feat/transfer-protection` (`1652880`, `43368ff`; 32 files, ~4.2k lines; CI run 85 green on
  that branch) adds a point-in-time transfer check for a client and an evidence view for an analyst. It branches from the default branch
  (`ea5ca9c`) and predates server-side sessions, CSRF and roles (B-011). A trial merge onto the integration line (2026-11-25, scratch
  worktree, not committed) conflicts in 7 files (`src/nexora/api/main.py`, `src/nexora/settings.py`, `apps/web/src/app/App.tsx`,
  `apps/web/src/lib/api.ts`, `apps/web/src/lib/api-types.ts`, `apps/web/openapi.json`, `apps/web/playwright.config.ts`). More important than the text conflicts: it adds
  a second authentication mechanism (static header `X-Nexora-Transfer-Analyst-Token`) and unauthenticated `POST` routes, which contradicts the
  invariant "public surface = `login` + `session`" and the deny-by-default role check (a write route without a declared role stops the app).
* **Modules**: `src/nexora/api/routes/transfer_checks.py` (new, from the branch), `src/nexora/application/transfer_protection.py` (new, from the branch),
  `src/nexora/api/main.py`, `apps/web/src/features/transfer-protection/` (new, from the branch), `apps/web/src/lib/i18n.ts`, generated API files.
* **Depends on**: B-002.
* **Implementation**: after D-12, merge the branch onto the integration line (no rebase of the collaborator's commits); replace the static
  analyst token with the session + `requires("analyst")` model; decide whether the client check is a signed-in route (`viewer`) or a deliberately
  public demo route with rate limiting and its own threat-model entry; CSRF on every `POST`; regenerate the API client; keep the branch's tests
  and add authorization-matrix coverage; review the "client chooses an action" flow against the rule "no automatic action against customers".
* **Acceptance**: full gate green; authorization matrix covers the new routes; no second auth mechanism; the holdout results file is quoted
  only with its own limits (synthetic, the branch's protocol).
* **Tests**: the branch's `test_transfer_checks.py`, `test_transfer_protection.py`, `test_transfer_evaluation.py`, its E2E specs, plus
  `test_authorization.py` extended.
* **Expected improvement**: the collaborator's work ships on the same security model as the rest of the product.
* **Risk / rollback**: revert the merge commit; no migration is involved.
