# Execution ledger

Append-only. One entry per task attempt or session, newest last. Never edit a past entry — add a new one that
corrects it. Record commands and their **literal** results; mark anything not run as "not executed".

Entry template:

```
### L-NNNN · YYYY-MM-DD · B-0xx (or "session") · status: done | partial | blocked | abandoned
* Branch / commits: `branch` · `<sha>` …
* Changes: …
* Verification (commands → observed): …
* Not executed / limitations: …
* Findings or follow-ups (new H-nn / B-nn): …
* State file updated: yes/no
```

---

### L-0001 · 2026-11-21 · session (gesture/graph verification) · status: done
* Branch / commits: `graph-workspace-wip` · `7abd9a5` (on top of checkpoint `b9943f0`).
* Changes: reproduced and fixed four defects — MediaPipe not pre-bundled in Vite (full-page reload mid-session; the gesture E2E failed on every cold
  cache), worker network guard deleted `WebSocket` (now guards fetch/XHR/WebSocket/EventSource), MediaPipe's `INFO:` stderr logged as an error
  (`workerConsole.ts`), Cytoscape rejecting CSS Color 4 tokens (`canvasColor.ts`); added the real-webcam checklist (not executed) and the first
  `ZENCODER_*` handoff documents.
* Verification: ruff/format/mypy clean; pytest 190 passed; alembic head `0004` + check clean; vitest 99; vite build; Playwright 34 (cold cache) and
  34 against the production bundle with gateway headers; `.railway` check; pitch 17 unit + 29 E2E. GitHub CI run 64 → success `[CI]`.
* Not executed: Docker build locally, local ShellCheck, pip-audit, real webcam.
* State file updated: n/a (state file did not exist).

### L-0002 · 2026-11-22 · session (master handoff and audit) · status: done
* Branch / commits: `claude/peaceful-darwin-nrquu9` · base `7abd9a5` · handoff commit = `git log -1 --format=%H -- docs/handoff/MASTER_HANDOFF.md`.
* Changes: **documentation and probes only — no product code changed.** Added `MASTER_HANDOFF.md`, `EXECUTION_BACKLOG.md` (38 tasks, 6 waves),
  `NEXT_SESSION_PROMPT.md`, `EXECUTION_STATE.md`, this ledger, `probes/` (three measurement scripts + a gateway stand-in); added a "superseded"
  banner to the three earlier `ZENCODER_*` documents.
* Verification (all re-run by hand, literal results in MASTER_HANDOFF §2): ruff / format / mypy clean; pytest 190 passed (0 skipped); alembic head
  `0004`, no drift; OpenAPI no diff; tsc clean; vitest 99; vite build; Playwright 34 (cold cache); Playwright against the production bundle 34;
  `.railway` check; pitch lint + 17 unit + build + smoke + 29 E2E; `npm audit` 8 advisories. GitHub CI run 64 read through the API → success.
  Probes: pipeline 200k transfers 22.5 s / 381 MiB; graph read model hub 20k peers 215–640 ms; `cose` layout 200 nodes 1,150 ms, 300 nodes 2,791 ms.
* Not executed: Docker image build/compose (no daemon), local ShellCheck, `pip-audit`, real webcam, live Railway state, camera path through the
  real Nginx image, ORM load/publish at 200k rows.
* Findings: H-01 … H-24 registered in MASTER_HANDOFF §16 (new this session: H-01 migration collision, H-02 open CSV import, H-03 invalid JSON logs,
  H-04 layout freeze, H-05 camera-before-model, H-06 N+1/over-fetch, H-08 benchmark arithmetic, H-10…H-22 design risks, H-23, H-24); four unmerged
  branches discovered (eloquent-planck, great-lovelace, admiring-fermat, sharp-cannon) plus the stale peaceful-babbage.
* State file updated: yes (created).

### L-0003 · 2026-11-22 · session (CI failure on the handoff commit) · status: done
* Branch / commits: `claude/peaceful-darwin-nrquu9` · base `da681c2` (docs only) → the commit that touches `apps/web/e2e/auth.spec.ts` and this ledger.
* Trigger: GitHub CI run 65 on `da681c2` failed in *Browser E2E* — one test, `auth.spec.ts` "an ended session sends the analyst to sign in and back to where
  they were", timed out at 60 s (33 of 34 passed; the other two jobs were green). The commit changed no product code and the same test had passed on identical
  code in runs 63 and 64, so the failure was an intermittent race that predates it.
* Root cause (test determinism, not a product defect): the test clears the cookies and then clicks a rail link, assuming no API request happens in between.
  `networkidle` cannot guarantee that. Any request that reaches the server first after the cookies are gone discovers the ended session, and the app (correctly)
  redirects to sign-in and replaces the whole shell; the click then targets a detached link. Evidence: 1 failure in 25 local repetitions of the real test;
  dispatching one `visibilitychange` (the app's own re-check) between `clearCookies()` and the click reproduced the exact CI signature (link resolved →
  "element was detached from the DOM, retrying" → timeout) **5 of 5**. What fired the late request in CI is **not proven** — the failure artifact lives on a host the
  agent proxy blocks, so the page snapshot could not be read.
* Fix: park all `**/api/**` requests until the click has navigated to `/lab`, then release them, so the first request to reach the server is deterministically one
  made from `/lab`. No assertion removed or loosened, no timeout raised; one stricter assertion added (`toHaveURL("/lab")`).
* Verification: the injected-disturbance test that failed 5/5 passes 10/10 with the fixed flow (scratch spec, deleted); the real test passes 60/60; `npx tsc -b`
  clean; full Playwright suite 34 passed including all 10 auth tests.
* Not executed: no further stress batches (stopped on the owner's instruction); CI result for the fix commit is recorded in the commit that follows, if any.
* Follow-up: none needed for the product. A future change that adds background API calls to the shell should keep this test's parking.
* State file updated: yes.

### L-0004 · 2026-11-22 · session baseline (fresh container) · status: done
* Branch: `claude/peaceful-darwin-nrquu9` at `0c8d21b`; `git fetch --prune` matched EXECUTION_STATE (open PR list not re-read: no difference
  in refs). **Push policy for this session**: the harness allows pushes only to `claude/peaceful-darwin-nrquu9`, so each task is developed
  on a local `feat/b-0xx-*` branch and fast-forwarded into the working branch after its gate passes (no `feat/*` branches on GitHub).
* Environment: PostgreSQL 16 started; the `nexora` role and `nexora`, `nexora_test`, `nexora_e2e` databases did not exist in this container
  and were created per `docs/development/local-setup.md`.
* Verification (commands → observed): `ruff check` All checks passed · `ruff format --check` 87 files already formatted · `mypy` no issues in
  61 source files · `pytest -p no:cacheprovider -rs` **190 passed**, 0 skipped · `alembic upgrade head` → `0004`, `alembic check` No new upgrade
  operations detected · `tsc -b` clean · `vitest run` **99 passed** · `vite build` built · `gen:api` + `git diff --exit-code` no diff ·
  `rm -rf node_modules/.vite && playwright test --trace off` **34 passed** (2.1 m) · `.railway` `npm run check` 3 services + database, all
  invariants hold. Matches the handoff exactly.
* Not executed: Docker, ShellCheck, pip-audit, webcam, live Railway (unchanged constraints).
* State file updated: no (baseline only).

### L-0005 · 2026-11-22 · B-001 · status: done
* Branch / commits: `feat/b-001-migration-chain-guard` → fast-forwarded into `claude/peaceful-darwin-nrquu9` (commit "B-001: …").
* Changes: `tests/unit/test_migration_chain.py` (new) — `chain_problems()` parses every file in `migrations/versions` itself (Alembic only
  warns on a duplicate id) and reports: duplicate ids, filename ≠ revision prefix, non-four-digit ids, merge revisions, missing parents,
  more than one base or head, branch points, gaps in the 0001… sequence, wrong `down_revision`; `0001`–`0004` pinned by SHA-256 and by the
  table each creates (`0003` → `users`, `0004` → `hypothesis_assessments`). 10 tests incl. the H-01 collision, two heads, renumbering/swap,
  edits. `tests/integration/test_migrations.py` (new) — upgrades `0002 → 0003 → head` in a throwaway schema (`search_path`), keeps a user
  row created at `0003`, then `compare_metadata` = [] (alembic-check equivalent). `migrations/env.py` accepts a caller-supplied connection
  (`config.attributes["connection"]`, the standard Alembic recipe; default path unchanged). CI "Migrations apply and match ORM" now fails
  unless `alembic heads` prints exactly one line. `docs/development/testing.md` documents the migration rules.
* Verification: reproduced H-01 with the real files (stoic-dijkstra's versions + quirky-ride's `0003_hypothesis_assessments.py`) →
  checker reports "revision '0003' defined more than once", "revision '0002' has 2 children". `pytest tests/unit/test_migration_chain.py`
  10 passed; `pytest tests/integration/test_migrations.py` 1 passed (would fail if search_path were ignored: public is already at 0004);
  full gate: ruff clean, format 89 files, mypy clean, pytest **201 passed** 0 skipped, `alembic check` clean, `alembic heads` 1 line,
  Playwright **34 passed** cold cache. No web code changed (tsc/vitest not re-run for this task; covered by the baseline and next task).
* Not executed: the CI step itself (runs on push).
* State file updated: yes.

### L-0006 · 2026-11-22 · B-010 · status: done
* Branch / commits: `feat/b-010-gate-csv-import` → fast-forwarded into `claude/peaceful-darwin-nrquu9` (commit "B-010: …").
* Root cause detail: FastAPI parses a multipart body **before** it solves any dependency (`fastapi/routing.py` 0.163.1: `await
  request.form()` at line 455, `solve_dependencies` at 511), so a dependency-based gate would refuse only after receiving up to
  `max_upload_bytes`. Fix: a route-class override on this one route (`_CsvImportRoute`) that, while the switch is off, runs the same
  `enforce_authentication` as the global dependency (anonymous → 401 `AUTH_REQUIRED`, missing CSRF → 403 `CSRF_FAILED`, so nothing
  about the setting leaks) and then raises `403 CSV_IMPORT_DISABLED` without touching the body. With the switch on, the normal route
  runs unchanged (authentication once, via the global dependency).
* Changes: `Settings.allow_csv_import = False` (`NEXORA_ALLOW_CSV_IMPORT`); `routes/datasets.py` registers the import route with
  `add_api_route(..., route_class_override=_CsvImportRoute)`; `.railway/railway.ts` pins `"false"` on `api`; `.railway/check.ts` fails if the
  api literal is not `"false"` (absent counts as a failure) or if the worker receives the switch; `docker-compose.yml` and `.env.example`
  default false; `SECURITY.md` control row. The two tests that import CSVs opt in (`settings.allow_csv_import = True`). OpenAPI document
  unchanged (route still listed; `gen:api` → no diff). The SPA has no upload control, so no UI change.
* Tests (new, `tests/integration/test_api.py`): refused by default + no rows in `datasets`/`import_batches`/`transactions` + lab path still
  works; anonymous → 401 and missing CSRF → 403 before the gate; an ASGI-level probe shows the disabled route answers **without pulling the
  body** (`receive()` not called before `http.response.start`), with a positive control (switch on → body read first, 201).
  Before the fix: `git stash` of `src/` → 2 of the 3 new tests fail (the auth-first one is a guard and passes either way).
* Verification: ruff clean, format 89 files, mypy clean (one override-type error fixed), pytest **204 passed** 0 skipped; `gen:api` + diff →
  no change; `tsc -b` clean; vitest **99 passed**; `.railway` check passes, and with the literal flipped to `"true"` fails with "api keeps CSV
  import disabled"; Playwright cold cache **34 passed** (2.0 m).
* Not executed: Docker compose stack (no daemon).
* Decision assumed: D-4 default (off everywhere except an explicit local opt-in).
* State file updated: yes.

### L-0007 · 2026-11-22 · B-003 · status: done
* Branch / commits: `feat/b-003-benchmark-arithmetic` → fast-forwarded into `claude/peaceful-darwin-nrquu9`. Cherry-picked `65e3894`
  (sharp-cannon, screen rounding), `8c7f2ff` (F1 from counts + numerators), `1867d01` (dirty-tree fix); the artifact half of `d084a97` was
  **not** cherry-picked — regenerated instead. Then: runner porcelain fix, artifact regeneration commits, amendment A2, renderer fix.
* Conflicts resolved: `Evaluation.tsx` — kept the integration line's distinct-network P@5 headline (audit L-02) inside the new count-based
  `methodMetrics` model (added `MethodMetrics.p5Distinct`); `tests/unit/test_benchmark.py` — union of both assertions (numerators +
  `per_flagged_network` / `networks_with_duplicates`); `docs/assets/screenshots/evaluation.webp` — the cherry-picked image came from another UI
  lineage, so it was regenerated (below).
* Artifacts (scripts only, clean trees): `run_benchmark.py` at `3f87b95` (92.6 s); A2 committed **before** the sealed rerun;
  `run_sealed_evaluation.py --split sealed` at `e113df7` (88.6 s), `--split dev` (39.9 s). Field-by-field diff (scratch script) old → new, all
  three: **0 integer/count changes**; sealed and dev `decision`, `bootstrap`, `examples` identical; F1 changed by ≤ 1e-4 in 9 (bench, incl.
  holdout v2 0.6855 → 0.6854), 3 (sealed: B3, B1, B0) and 4 (dev) summaries; new `tp_high`/`fp_high`/`relevant`; latency, platform, timestamps,
  commit, harness hash differ. Generator and candidate/baseline config hashes verified unchanged before the rerun.
* New defect found and fixed (H-08 class): `scripts/run_benchmark.py` rendered `docs/EVALUATION.md` by re-rounding stored 4-decimal ratios to 3
  decimals; **18 table rows** carried a wrong third decimal (e.g. validation v2 FPR 36/85 = 0.42353 shown 0.423 → 0.424; holdout v2 high-band FPR
  8/128 = 0.0625 shown 0.062 → 0.063 half-up; validation v2 alert precision 50/157 = 0.31847 shown 0.319 → 0.318). Count-backed ratios now
  render once from counts (Decimal, half-up, as on the screen); added `--render-only` to re-render from the committed artifact.
  Also fixed the same porcelain-strip bug in `run_sealed_evaluation.py` as `1867d01` fixed in `run_benchmark.py`.
* Docs: README 79.4 % → 79.3 % (from the cherry-pick); `docs/evaluation/RESULTS.md` A2 note + provenance (tables unchanged at 3 decimals;
  median-ms columns marked as original-run values); `EXPERIMENT_PROTOCOL.md` amendment A2. README table re-checked against counts: all match.
  README screenshot regenerated on the dev stack (same 1440×900 viewport, `demo-v1 · seed 2026`, 2× → 1600×1000 webp): it showed 79,4 %, now
  79,3 %. Not produced through the Docker gateway smoke pipeline (no Docker here).
* Tests: Python `test_every_committed_ratio_recomputes_from_its_counts[bench-v1|dev|sealed]` (fails on all three old artifacts, passes now) and
  `test_report_rounds_count_backed_ratios_once`; vitest artifact-consistency test from `8c7f2ff` failed on the old artifact, passes now;
  `evaluation.spec.ts` asserts the headline reads `79,3 %`.
* Verification: ruff clean, format 89 files, mypy clean, pytest **210 passed** 0 skipped; gen:api in sync (schema change from `8c7f2ff` already
  carried its generated files); tsc clean; vitest **105 passed**; vite build ok; Playwright cold cache **34 passed**; visual check of
  `/analytics/benchmark` at 1440 and 390 px, dark and light: no horizontal overflow, empty console-error list (scratch spec, deleted).
* Not executed: Docker smoke screenshot pipeline. Pitch numbers (`apps/pitch`) untouched — B-004.
* State file updated: yes.

### L-0008 · 2026-11-22 · B-015 · status: done
* Branch / commits: `feat/b-015-structured-logging` → fast-forwarded into `claude/peaceful-darwin-nrquu9`.
* Changes: `src/nexora/logging_config.py` (new; named so it cannot be confused with the stdlib module) — `JsonFormatter` (`json.dumps` of
  `ts` UTC ms, `level`, `logger`, `msg`, `request_id` from the record or a `ContextVar`, `exc`, `stack`, plus any `extra=` fields; unserialisable
  values degrade to text; uvicorn's ANSI `color_message` dropped), `LOGGING_CONFIG` (root → stderr JSON; uvicorn loggers propagate) and
  `configure_logging()`. `configs/logging.json` is the same dict for uvicorn's `--log-config` (unit test asserts equality and that the Dockerfile
  CMD, `scripts/e2e_stack.sh` and `make api` pass it). API middleware sets the request-id context; the 500 and 503 handlers pass the envelope's
  `request_id` explicitly (they run outside the middleware). Worker uses `configure_logging()` instead of the unescaped format string.
  `docs/deployment/railway.md` documents the format and how to find a quoted id.
* Reproduction: `test_the_old_worker_format_was_invalid_json` — the old worker format string on `job failed: relation "transactions" does not
  exist` raises `JSONDecodeError`. The three request-id integration tests fail with `main.py` stashed and pass with it.
* Verification: unit 12 (hostile messages incl. quotes, backslashes, CR/LF, NUL, printf directives; tracebacks; extras; context vs explicit id;
  config parity; dictConfig routing of uvicorn loggers); integration 3 (forced 500 and forced `OperationalError` → a log line with the envelope's
  `request_id`; a client-supplied `X-Request-ID` is echoed and logged). Real uvicorn with `--log-config`: startup, access and shutdown lines are
  JSON and access lines carry the request id (incl. client-supplied `live-check-1`). Full gate: ruff clean, format 92 files, mypy clean (62
  files), pytest **224 passed** 0 skipped; tsc clean; vitest **105**; Playwright cold cache **34 passed**; all 592 `[WebServer]` JSON lines in
  that run parse.
* Not executed: Docker image (the CMD change is exercised by CI's image job). Alembic's own CLI output (pre-deploy migration, disposable resets)
  stays plain text — a separate one-shot process configured by `alembic.ini`; the gateway keeps Nginx's format.
* Follow-up: B-016 can now log job events as structured `extra=` fields.
* State file updated: yes.

### L-0009 · 2026-11-22 · B-012 · status: done
* Branch / commits: `feat/b-012-react-router-v7` → fast-forwarded into `claude/peaceful-darwin-nrquu9`.
* Changes: `react-router-dom@^6.30.6` replaced by `react-router@^7.18.6` (v7's canonical package; `react-router-dom` is only a compatibility
  re-export), imports in 14 files rewritten `react-router-dom` → `react-router`. No code changes needed: the app uses declarative `BrowserRouter`
  routing only (the data-router future flags do not apply); the one splat route navigates to an absolute path, and no relative `to`/`navigate`
  exists (grep), so `v7_relativeSplatPath` changes nothing; navigation state updates are now wrapped in `startTransition` (v7 default).
  Dependabot PR #10 (react-router-dom 7.18.5) is superseded by this change — left for the owner to close.
* Verification: `npm audit --omit=dev` before → 2 moderate (GHSA-wrjc-x8rr-h8h6 open redirect, GHSA-337j-9hxr-rhxg SSR); after → **found 0
  vulnerabilities**. `tsc -b` clean; vitest **105**; `vite build` ok — main chunk 296.58 → 312.93 kB (gzip 99.60 → 105.34 kB, +5.7 kB: v7 core);
  Playwright cold cache **34 passed** (incl. the sign-in return-to flows and graph URL filters surviving reload). Scratch spec (deleted): every
  route, the `/evaluation` redirect, the `*` fallback, rail navigation into three lazy chunks and browser back — **zero console warnings or
  errors** (the v6 future-flag warnings are gone).
* Not executed: production-bundle run through the gateway stand-in (CI's image job covers the real gateway).
* State file updated: yes.

### L-0010 · 2026-11-22 · B-031 · status: done
* Branch / commits: `feat/b-031-model-before-camera` → fast-forwarded into `claude/peaceful-darwin-nrquu9`.
* Changes: `GestureSession.start()` now loads the engine first (`ui: "loading"`), requests the camera only after the engine reports ready
  (`"starting"`), then calibrates; every exit path still goes through `teardown()` (generation counter unchanged). An optional constructor
  seam (`GestureDeps`: camera/engine factories, `CameraPort`/`EnginePort`) makes the order unit-testable; production wiring identical.
  UI follow-up found during the visual check: the panel showed **"Камера включена"**, an empty preview box and a "Выключить камеру" button while
  the camera was not on (that was already wrong during `starting` before this change). Now the badge and preview appear only from calibration,
  and the toggle/stop control reads *Отменить включение* (`gesture.cancel`, new i18n key) until the camera is live.
  `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` steps 3–4 updated for the new order (still **not executed** on real hardware — B-030).
* Tests: `gestureSession.test.ts` (8, new): order loading → starting → calibrating with no camera object before the engine is ready; stop /
  hidden tab / model failure while loading never touch the camera; stop during the prompt and a late grant release everything; denial disposes
  the loaded engine; engine failure during the prompt stops the camera; camera ending mid-session. E2E (new) holds `/vendor/mediapipe/**` with
  `context.route`: while "Загрузка модели…" is shown `getUserMedia` calls = 0 and live tracks = 0, no "Камера включена", button "Отменить
  включение"; after release: 1 call, 1 track, badge and "Выключить камеру". **On the old ordering this E2E fails** (`getUserMedia` calls:
  expected 0, received 1). Existing gesture E2E unchanged and green (the denial test still passes without a longer timeout).
* Verification: tsc clean; vitest **113**; vite build ok; Playwright cold cache **35 passed**; panel screenshots during loading and live, dark
  and light (scratch spec, deleted). Python untouched (last full Python gate: L-0008, 224 passed).
* Behaviour note: the browser prompt now appears after the model has loaded (a second or so locally, longer on slow links), not right after the
  click; `getUserMedia` does not require transient user activation in Chromium, Firefox or Safari. Real browsers other than Chromium: B-032.
* State file updated: yes.
