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

### L-0011 · 2026-11-22 · B-020 · status: done
* Branch / commits: `feat/b-020-layout-worker` → fast-forwarded into `claude/peaceful-darwin-nrquu9`. Decision D-7 taken as recommended
  (worker + cache, same algorithm).
* Reproduction (Chromium, dev server, graph response replaced by a deterministic n-account graph): one long task of **750 ms at 100 accounts,
  2,462 ms at 200**; at 300 the canvas did not appear within the 5 s expect timeout. CPU profile of the new mount: no application hotspot,
  remaining main-thread time is Cytoscape's own style/draw.
* Changes (`apps/web/src/components/graph/`): `coseLayout.ts` (pure `computeCoseLayout` — same cose options, `randomize: false`; node sizes
  passed in; `layoutKey` = length-prefixed FNV fingerprint of every input), `layoutWorker.ts` (module worker; says "ready" once loaded),
  `layoutClient.ts` (one worker per canvas, work sent only after "ready", a superseded *computing* job terminates the worker, an unsent one
  is replaced, `dispose()` terminates — a loading worker as soon as it is ready; LRU cache of 24 layouts; synchronous fallback if workers are
  unavailable or crash). `GraphCanvas.tsx`: sizes measured on a headless styled instance; the drawn instance is created only once positions
  exist (cache hit → synchronously); while pending the stage shows the existing loading shimmer plus a visible, announced "Раскладка графа…"
  (`graph.layingOut`), `aria-busy`, `data-layout="pending|ready"` (rendered from state from the first frame); `performance.mark`s bracket the
  off-thread layout; selection/emphasis re-applied to a new instance (`epoch`).
* Defects found on the way and fixed: (1) headless Cytoscape defaults to the `null` layout, which put every node at (0,0) — cose then
  consulted `Math.random` ~3,500 times per run and the picture changed on every load (caught by the existing determinism E2E); fixed with
  `layout: { name: "preset" }`, unit test asserts no `Math.random` call. (2) Terminating a still-loading worker (React StrictMode double mount in
  dev) left its module requests dangling, so Playwright's `networkidle` never fired (mobile spec) — fixed by the ready handshake.
  (3) `GestureSession.start()` silently ignored a click while the graph had no controller (now a real window during layout); the click is now
  remembered and honoured when the controller attaches (dropped on dismiss/stop); 2 unit tests.
* Deliberate behaviour change: cose used the container size as its gravity centre, so the picture depended on the viewport (and a 0-sized
  container centred it at the origin). The worker's headless instance has a fixed centre near the seeds' centre, so the same snapshot now gives
  the same arrangement on every screen size; the canvas still fits it to the stage. The determinism E2E (same snapshot, same picture) passes
  unchanged. No position animation any more (the stage shows the result once, faded in with `--dur-2`, instant for reduced motion).
* After (production bundle via `gateway_sim.mjs` with the generated CSP): worker time 374 / 1,618 / 2,645 / 3,879 ms at 100 / 200 / 300 / 400
  accounts; **no long task while the worker computes at any size**; largest main-thread tasks: setup 67–229 ms before, drawing the result
  64–199 ms after. Worker chunk `layoutWorker-*.js` 452 kB (its own Cytoscape copy; fetched by the graph page only). `worker-src 'self'` allows it.
* Tests: `coseLayout.test.ts` 5 (determinism, no Math.random, finite distinct positions, stray edges, key sensitivity and separator safety),
  `layoutClient.test.ts` 8 (cache, supersede-terminates, loading worker kept and only the latest sent, dispose while loading / computing,
  crash fallback, no-Worker fallback, LRU bound), gesture 2; E2E: "a 300-account view lays out in a worker" (no long task > 200 ms inside the
  layout window, none ≥ 1 s from navigation to a drawn graph, returning to the view reuses the cached layout). `stageSettled` and the gesture
  `openGraph` now wait for `data-layout="ready"` instead of a fixed 900 ms. On the old canvas the new E2E fails at the ready signal (the
  quantitative before-evidence is the reproduction above).
* Verification: tsc clean; vitest **128**; vite build; Playwright cold cache **36 passed**; the same suite against the production bundle with the
  gateway CSP headers **36 passed**; gestures 20/20 over 4 repetitions; graph-workspace 18/18 over 3; visual check of pending and ready states,
  dark/light, 1440 and 390 px (scratch specs, deleted).
* Not executed: real Nginx image (CI covers it); browsers other than Chromium.
* State file updated: yes.

### L-0012 · 2026-11-23 · session resume · status: done
* The container restarted between B-020's last verification and its commit (PostgreSQL down, date rolled over). Working tree intact on
  `feat/b-020-layout-worker`; databases survived. Re-verified before committing: tsc clean, vitest 128, Playwright cold **36 passed**. B-020
  committed as `0340f1a`. CI: runs 72 (B-012) and 73 (B-031) success.

### L-0013 · 2026-11-23 · B-041 · status: done
* Branch / commits: `feat/b-041-entity-metrics` → fast-forwarded into `claude/peaceful-darwin-nrquu9` (code `85f8b5e`, bench artifact, dev
  artifact, docs).
* Changes: `src/nexora/evaluation/entity_metrics.py` (new, pure): account-level tp/fp/fn against complete truth lists with false positives split
  into labelled-legitimate vs unlabelled background accounts; distinct-network precision–recall over the pooled analyst queue (ties grouped, so
  order-independent; integer curve points; AP recomputable from them); planted share per band with Wilson 95 % intervals; 2,000-draw dataset
  bootstrap (seed 20261123) for account recall/precision and AP. `summarize()` unchanged (it is called thousands of times inside the sealed
  runner's bootstrap). Scripts attach `entity` per method; `EVALUATION.md` renders it from counts. `MethodSummary.entity` optional in the API
  schema (older artifacts validate); OpenAPI client regenerated.
* Artifacts: `bench-v1.json` regenerated at `85f8b5e` (clean): 0 count changes, 0 F1 changes, `entity` added to 23 summaries.
  `dev-evaluation.json` at `5bfc0bb`: decision/bootstrap/examples identical, 0 count changes, `entity` on 11 summaries.
  `sealed-evaluation.json` deliberately **not** re-run (consumed; RESULTS.md says why). No README/pitch claim uses the new metrics.
* Observation, not a claim (synthetic, exposed holdout): the bench-v1 table shows `insufficient_evidence` 8/8 planted — the known L-01 leak made
  visible by the new reliability view.
* Tests: `test_entity_metrics.py` 12 (hand-computed fixture: account counts, distinct-network curve with a tie and a duplicate, AP = 0.5,
  tie/input-order independence, Wilson reference values 5/10 → 0.2366–0.7634 etc., bootstrap determinism); the artifact-consistency test now
  recomputes every entity ratio, AP and Wilson interval from counts for all three artifacts.
* Verification: ruff clean (incl. scripts), format 98 files, mypy clean (63 files), pytest **236 passed** 0 skipped; gen:api regenerated; tsc
  clean; vitest **128**; Playwright cold **36 passed**.
* State file updated: yes.

### L-0014 · 2026-11-23 · lint slip in B-041 · status: done
* `d5dae0d` contained a test edit verified with pytest but not re-linted (ruff B905/RUF007 in `tests/unit/test_benchmark.py`), so CI's lint
  step would fail on it. Fixed and pushed alone as `84fa317` before any further work. Rule kept from here on: re-run the whole lint/format/
  mypy gate after the last edit, not just pytest.

### L-0015 · 2026-11-23 · B-040 · status: done
* Commits: lock `c6dbc6b` (generator, tests, runner, protocol — **pushed before the run**), artifact commit (unchanged run output), then
  docs/test commit; working branch fast-forwarded and pushed.
* Generator `src/nexora/evaluation/sealed_generator_v2.py` (v1 untouched): seeds 9100–9179 (80), 60-day window from 2026-05-04, log-normal
  amounts, business-hours timing and weekend shifts, changed ranges; new families SV2 two-tier collection, SV3 scatter-gather, SV11 salary-like
  pass-through, LV10 merchant with unobserved outflows, LV11 property escrow, LV12 payroll agency, LV13 group gift; label-blind boundaries
  (5 % sample of accounts present in the data from an independent seed stream + boundary centres of **both** labels); truth lists = exactly
  the accounts in the scenario's transactions. `benchmark.py`: split `sealed_v2`, `CONSUMED_SPLITS = {"sealed"}`. Runner: per-split protocol,
  generator hash, artifact name; also hashes `entity_metrics.py` and itself.
* Generator tests (10, data only — no detector ran on sealed-v2 before the lock): they caught builders listing accounts that never transact
  (and the boundary sample drawing them) — fixed. The same data check on sealed-v1: 4/1,740 suspicious and 45 legitimate truth accounts and
  9 declared boundary accounts never occur in any row (v1 scenario-level results unaffected; v1 consumed, not re-run) — new finding **H-25**.
* Run: clean tree at `c6dbc6b`, 276 s; hashes equal the pinned ones. **Pre-registered outcome: replicated** (recall 191→197/262, CI +0.0075…
  +0.0428; FPR 191→100/394, CI −0.2745…−0.1896; high-band FPR 92→82/394, CI −0.0418…−0.0102; distinct P@5 0.3881→0.4358, CI +0.0271…
  +0.0696). Re-run at `1a387ce`: identical except latency/runtime/timestamp/commit. Synthetic data only.
* Descriptive findings (for B-043/B-044/B-045/B-046 — to be addressed on dev/adversarial dev only, never tuned on sealed-v2): new legitimate
  lookalikes reach high bands (payroll agency 25/25 flagged, event ticketing 32/42, group gift 20/29, property escrow 11/32; candidate
  high-band FPR 0.208 vs 0.098 on v1); misses: salary-like pass-through 0/17, recurring mules 1/12; `critical` 4/10 planted vs `high` 279/368;
  abstentions 34/166 planted (label-blind boundaries work; bench-v1 showed 8/8).
* Verification: ruff/format/mypy clean; pytest **246 passed** at the lock (+1 consistency case after the artifact: test_benchmark 26 passed).
  No web change.
* State file updated: yes.

### L-0016 · 2026-11-23 · session (parallel recovery) + probe correction · status: done
* Context: a second session (`session_01YM4H2Tng9fXjo91qVvavzm`) was started on this branch with a recovery prompt stating that B-020 had
  not been committed. Its container held the branch at `0c8d21b`; after fast-forwarding to `d0cb21e` it found no B-020 commit anywhere and
  re-implemented B-020 (local commit `6cb45bb`, full gate green: pytest 224, vitest 131, Playwright 37 cold cache, 37 against the production
  bundle with CSP). Its push was rejected: meanwhile the original session (`session_01YM4H2WosRxmPZ3JnYgB7uc`) had pushed its own B-020
  (`0340f1a`, CI run 74 success) and then B-041/B-040 (`0dd9cd7`, CI run 78 success). **The duplicate B-020 was not pushed or merged**; the
  branch was aligned with `origin` (no force, no history rewritten). Two sessions on one branch with the same backlog is a coordination
  hazard — the owner decides which one continues (B-011 is marked Active by the original session).
* Change in this entry: `docs/handoff/probes/cose_layout.mjs` corrected (explicit preset layout and drawn node sizes, as `coseLayout.ts`
  does; also runs the old setup for comparison and counts `Math.random` draws); README and H-04 annotated with the corrected figures.
  Observed (4 cores): app 50 nodes 63 ms · 100: 199 · 200: 779 · 300: 1948 · 400: 3138, 0 random draws; old setup 300: 1695 ms with
  89,700 draws. No product code changed.
* Observations on the delivered B-020, from comparing the two implementations (not acted on; candidate follow-ups for the owner):
  (1) on every relayout (filter change, expansion) the stage is emptied and shows only the status until the worker finishes — up to
  ~2.6 s at 300 accounts — whereas keeping the previous drawing until the new positions exist avoids the blank stage; (2) L-0011 reports
  main-thread setup tasks of 67–229 ms, i.e. up to 29 ms over the 200 ms acceptance threshold outside the measured layout window; the
  alternative measured 138–165 ms for the whole 300-account path. The alternative is kept as a patch outside the repository.
* Verification: `python3 docs/handoff/probes/check_handoff_docs.py` → OK; probe output above is literal.
* State file updated: no (its Active task belongs to the original session).

### L-0017 · 2026-11-23 · session recovery; handoff checker and finding H-25 · status: done
* Session `session_01YM4H2VbXza5W7vAoVxRamj`. Recovery: the container held the branch at `0c8d21b`, 24 commits behind
  `origin/claude/peaceful-darwin-nrquu9` = `3528265` (fast-forward, no local work); every SHA of L-0005…L-0016 is reachable
  from origin; CI run 79 on `3528265` success. The other two sessions on this branch were idle (session list) before any
  write. Correction to L-0016: its "checker → OK" does not reproduce on a fresh checkout — 4 problems (that container
  had built the web app and still held its local B-020 commit); the commit message of `3528265` says 2.
* Checker (`docs/handoff/probes/check_handoff_docs.py`), root causes, each reproduced: (1) the prose idiom "docs/test
  commit" (L-0015, docs and tests) read as a path — 409 of 411 path tokens sit in code spans or link targets, the other
  two are `configs/detectors.yaml` (real) and that idiom; prose tokens now count only when unambiguous (two segments
  below the top level, an extension or a trailing slash), code spans are checked as before. (2)
  `apps/web/public/vendor/mediapipe/` is git-ignored build output: present only where `vite build` ran — ignored paths
  are now counted as generated, not checked. (3) The local-only B-020 duplicate named in L-0016 passed in the container
  that held it and failed everywhere else — commits must now be reachable from HEAD or an origin branch, a deliberately
  unpublished one is written as "local commit" + SHA (L-0016 already is). (4) H-25 was referenced, never defined.
  Refactored into functions (sections 4–6 unchanged); old checker on this tree: 4 problems; new: H-25 only, then OK.
  Path coverage unchanged otherwise: 387 checked + 1 git-ignored + 1 prose idiom = the old 389.
* H-25 defined in MASTER_HANDOFF §16.1 after re-measuring it: sealed-v1 4/1,740 suspicious, 45/5,099 legitimate-only,
  9/872 boundary (as L-0015 said) **and** the development generator too — holdout 1/735 suspicious, legitimate-only
  25/10/17 on dev/validation/holdout; sealed-v2 0. Published impact: `bench-v1` holdout account recall understated by
  ≤ 0.0013, ordering unchanged; network-level metrics unaffected by construction (asserted). No artifact or generator
  touched. New tasks: B-048 (metric-definition fix, owner decides), B-025 (B-020 follow-up: blank stage on relayout and
  the unmeasured sizing probe before `LAYOUT_MARK_START`, confirmed in `GraphCanvas.tsx`).
* Tests: `tests/unit/test_handoff_docs_checker.py` (15: the reported idiom, same token in code still checked,
  unambiguous prose still checked, similar prefixes, exemptions, link/fence spans, broken vs valid, git-ignored, local
  vs unknown vs unpublished commits); `tests/unit/test_truth_account_presence.py` (6: exact H-25 counts per split,
  sealed-v2 = 0, ≥ 2 transacting accounts per scenario).
* Verification: checker OK (399 paths, 40 tasks, 25 findings); ruff, format, mypy clean; pytest **268 passed**, 0 skipped
  (local PostgreSQL 16, databases created per `docs/development/local-setup.md`). No web change, web gates not re-run.
* State file updated: yes.

### L-0018 · 2026-11-23 · B-011 · status: done
* Session `session_01YM4H2VbXza5W7vAoVxRamj`, branch `claude/peaceful-darwin-nrquu9` (no other session active; remote unchanged since L-0017).
* Policy: the backlog's documented model (viewer < analyst < admin), not the admin/manager/analyst set in the session prompt —
  no `manager` duty exists in the product. Matrix in MASTER_HANDOFF §11: every read for every role; writes `analyst`;
  `POST /datasets/import` `admin` (new decision D-11, assumed; one line to relax); logout any role; roles changed only by the
  operator CLI (`create-user --role`, `set-role`, which ends the user's sessions and is audited `user.set_role`). Roles are
  global; dataset visibility stays B-019 (D-3); no tenant model exists to isolate.
* Implementation: migration `0005` (`users.role` NOT NULL DEFAULT 'analyst' + CHECK; additive, reversible — upgrade/downgrade
  round trip run; legacy accounts become analyst = unchanged permissions); `auth/roles.py`; `Principal.role` read from the
  user row on every request (a lowered role applies to the next request); `api/deps.py` `requires(...)` per route and
  `check_route_roles` at app build: a write route without a declared role stops the app from starting (deny by default).
  The import gate checks the role before the multipart body is read (same reason as B-010) and therefore authenticates
  once more than other routes on that path only. `AuthUser.role` in the API (OpenAPI client regenerated). UI: `useCan()`
  hides open-case / decision / note / generate / analyse for viewers and says why (i18n); the account card shows the role.
* Found while testing: FastAPI 0.163 keeps included routers as lazy `_IncludedRouter` entries, so `app.routes` lists none
  of the API routes — a check iterating it would pass vacuously. Uses `fastapi.routing.iter_route_contexts`, and refuses
  an app in which it finds no `/api` route at all.
* Tests: `tests/integration/test_authorization.py` (13: documented matrix == declared; every OpenAPI operation × each role
  → `FORBIDDEN_ROLE` iff below minimum, identical message without role names; viewer reads all and changes nothing, row
  counts unchanged; auth and CSRF before role; no API input carries a role; login ignores a role field; role read per
  request; `set_role` ends sessions + audit; defaults, unknown roles refused by service and by the database CHECK; CLI);
  `tests/unit/test_roles.py` (14); analyst refused by role before the upload is read with import on; legacy row backfilled
  in the stepwise migration test; migration-chain tests made head-relative (they hard-coded `0005` as "the next free
  revision"); import tests that ran as analyst now run as admin (D-11). Mutation checks: lowering `notes` to viewer → 2
  failures; removing its declaration → app refuses to build. Web: vitest +7 (`roleAllows`); E2E viewer journey.
* Visual check (scratch spec, deleted): viewer at 1440 and 390 px — fixed three things it showed: role truncated in the
  account card, the lab empty state told a viewer to generate, the case hint told a viewer to open a case.
* Verification: ruff, format, mypy clean; pytest **296 passed**, 0 skipped; `alembic upgrade head` + `alembic check` clean,
  single head `0005`; gen:api idempotent; tsc clean; vitest **135**; Playwright cold cache **37 passed**; checker OK.
  Not run: production-bundle CSP run (no change to headers or assets), Docker image.
* Production note: deploying `0005` makes every existing account an analyst (current behaviour). Nothing deployed (B-055).
* State file updated: yes.

### L-0019 · 2026-11-23 · CI record and session end · status: done
* CI: run 80 on `b47ac73` (L-0017) success; run 81 on `7b456e3` (B-011) success in all three jobs — tests and browser E2E,
  production images + gateway smoke, Railway definition + ShellCheck.
* Next task: B-004. It merges `admiring-fermat-9fc4nx` (pitch, ~3.9k lines) and `great-lovelace-0gmpmi` (README redesign,
  conflicts in `README.md`) into the working line; not started in this session because it could not be finished and
  verified (pitch unit + 29 E2E) within it. Open owner decisions touched by this session: D-11 (import role), B-048 (H-25 fix).

### L-0020 · 2026-11-25 · session recovery, branch consolidation, completion-management system · status: done
* Session `session_01YM4H2XZynKHHiV6ksQW3Rh`; harness-assigned branch `graph-workspace-wip`.
* Recovery (read-only first): `git fetch --prune`; no `main` ref is served (default branch `claude/brave-dirac-c80nwq` = `ea5ca9c`);
  `graph-workspace-wip` was at `0c8d21b`, `claude/peaceful-darwin-nrquu9` at `bd3868f` = 27 commits ahead of it, 0 behind (strict
  fast-forward; last commit 2026-11-23 07:10, no session active since). GitHub: CI runs 80–82 on `peaceful-darwin` success; run 85 on
  `feat/transfer-protection` success; CodeQL on the default branch success (2026-11-23). Open PRs #3, #5, #15, Dependabot #6–#14, #16.
* Consolidation: `git merge --ff-only origin/claude/peaceful-darwin-nrquu9`, `git push origin graph-workspace-wip` →
  `0c8d21b..bd3868f` (fast-forward, no rewrite). `graph-workspace-wip` is the working line from here on.
* New finding H-26 / task B-056 / decision D-12: `feat/transfer-protection` (collaborator, 2 commits on `ea5ca9c`, ~4.2k lines) is
  not integrated. Trial `git merge --no-commit` in a scratch worktree (removed afterwards, nothing committed): conflicts in 7 files;
  adds unauthenticated `POST /api/v1/demo/transfer-checks` and a static-header analyst token — incompatible with sessions/CSRF/B-011.
* Baseline on `bd3868f` (fresh container; PostgreSQL role and three databases created via `su postgres -c`): ruff, format (102 files),
  mypy (65 files) clean; pytest **296 passed, 0 failed, 0 skipped** (junit XML, 34.1 s); `alembic upgrade head` 0001→0005,
  `alembic check` "No new upgrade operations detected", `alembic heads` `0005 (head)`; `tsc -b` clean; vitest **135 passed** (15 files);
  `vite build` ok; `npm run gen:api` → no diff; Playwright cold cache **37 passed** (2.2 min); `.railway` `npm run check` "3 services +
  database, all deployment invariants hold"; pitch lint clean, tsc clean, vitest **17 passed**, build ok, Playwright **29 passed**;
  `npm audit --omit=dev` (web) **0 vulnerabilities**; `npm audit` (web, incl. dev) 6 (3 moderate, 1 high, 2 critical; vitest 2 /
  esbuild / tinypool chain). Handoff checker OK.
* Management system extended (not duplicated): one machine-read `Status` line per backlog task with commit + ledger evidence for the
  ten done tasks; **Critical path** convention line; `docs/handoff/probes/progress.py` (weighted completion per the protocol formula,
  critical-path progress, blocked/open-P0 lists, evidence check: DONE needs a reachable commit and an existing ledger entry; `--mermaid`
  generates the dependency graph); `docs/handoff/DEPENDENCY_MAP.md` (generated graph + critical path + parallel streams),
  `RISK_REGISTER.md` (supersedes MASTER_HANDOFF §22), `TEST_MATRIX.md`, `RELEASE_CHECKLIST.md`; `docs/completion/README.md` maps the
  protocol's requested document set onto these single sources. CI test job now checks out full history (`fetch-depth: 0`) so the
  evidence test can prove reachability; without it a depth-1 clone could not.
* Tests: `tests/unit/test_progress_probe.py` (8: formula, VERIFIED ≠ DONE, evidence rules, malformed/missing/duplicate status lines,
  real backlog consistent, DEPENDENCY_MAP block equals the generated graph, edges from Depends on). Mutation checks: removing B-001's
  commit from its status line → probe exits 1 ("DONE must read…"); hand-editing one diagram line → drift test fails.
* Computed progress: 34.6 % weighted verified completion; critical path 42.5 %; 41 tasks, 10 done; open P0: B-002, B-030 (both human).
* Not executed: Docker, ShellCheck, pip-audit, real webcam, live Railway, Playwright against the production bundle (no change to
  product code or headers in this entry).
* State file updated: yes.

### L-0021 · 2026-11-25 · B-004 · status: done locally (DONE after CI)
* Branch / commits: `graph-workspace-wip`, merge commit of `origin/claude/great-lovelace-0gmpmi` (`058a273`, which contains
  `admiring-fermat-9fc4nx` `ced8227`); the collaborator-visible original commits are preserved (no cherry-pick, no rebase).
* Merge: only `README.md` conflicted (7 hunks); every other change is confined to `apps/pitch/**` (redesign replaces the first pitch),
  `docs/assets/readme/` and `scripts/render_readme_figures.py`; nothing under `apps/web`, `src`, `migrations` changed.
* Finding H-27 (new): `bench-v1.json` is `risk-policy-v2` (config `489b477a…`), the branch ships `risk-policy-v3`; the live demo is
  `f29ae56` = v2. README resolved on the redesign's structure with every stale claim corrected: named accounts and roles instead of
  "shared login / one demo analyst / no role model"; the "PR #3 not merged" warning replaced by the exposed-holdout warning; artifact
  commit `85f8b5e` (was `58440cc`); a second table with the pre-registered `sealed-v2` result of v3 (read from
  `benchmarks/results/sealed-v2-evaluation.json`: rules 257/262, 374/394, 71.34; v2 191/262, 191/394, 8.62; v3 197/262, 100/394,
  6.42; decision `improvement`) and a caution that evaluating a changed configuration spends a sealed-v2 use; graph workspace and
  experimental gestures described (tested only with a simulated camera); roadmap and limitations brought up to date.
* Pitch: `apps/pitch/scripts/extract-bench.mjs` (run from `apps/pitch`) re-extracted the excerpt — diff = commit, F1 −1e-4 (A2), new numerator fields; every count
  identical. Slide 6 label now says "конфигурация v2 (как в демо)"; `bench.test.ts` pins `policy_version == risk-policy-v2`.
  README figure re-rendered by `scripts/render_readme_figures.py`; caption now carries the policy version read from the artifact.
* New tests: `tests/unit/test_readme_numbers.py` (3) recompute every README benchmark figure from its artifact. Mutation: README
  `25.4 % (100/394)` → `25.3 %` → `test_sealed_v2_figures_match_the_artifact` fails; restored → passes.
* CI: the separate `.github/workflows/pitch.yml` (path-filtered on `apps/pitch/**` and `bench-v1.json`) already runs the pitch's
  lint, types, unit, build, server smoke and E2E; the merge updates it to the redesign's version. (I first added a duplicate job
  to `ci.yml` and the L-0020 test matrix said "not in CI" — both wrong, both corrected before this commit.)
* Verification: ruff (incl. `scripts`), format, mypy clean; pytest **307 passed, 0 skipped**; pitch lint clean, tsc clean, vitest
  **14 passed**, build ok, Playwright **31 passed**; handoff checker OK; progress probe exit 0. Visual: slide 6 at 1440×900 (label
  wraps cleanly, commit `85f8b5e`), 390 px portrait shows the deck's existing rotate-device prompt; README SVG caption fits.
  Not run: web Playwright (no `apps/web` change), Docker.
* Follow-up: B-057 (move headline + results slide to v3 / sealed-v2 after deployment, B-055).
* State file updated: yes.

### L-0022 · 2026-11-25 · B-014 · status: done
* B-004 CI outcome (L-0021's commit): ci run 88 on `4599aa9` failed in one Browser E2E test (`auth.spec.ts`, ended session) —
  not caused by B-004 (no `apps/web` file changed); root-caused and fixed as H-28 (L-0023). Pitch workflow run 6 on
  `4599aa9` success; ci run 89 on its descendant `8e4cdd9` (which contains every B-004 file unchanged) success in all three
  jobs. B-004 is marked DONE on that evidence.
* Branch / commits: `graph-workspace-wip` · `8e4cdd9` (gate) and the L-0023 commit (controls must name the planted finding).
* Changes: `.github/workflows/audit.yml` (push/PR on lockfiles and manifests, weekly, manual): `npm audit --omit=dev
  --audit-level=high` for `apps/web`, `apps/pitch`, `.railway`; `pip-audit==2.9.0 --disable-pip --require-hashes` over
  `uv export --frozen --no-dev --no-emit-project`; dev advisories reported to the job summary only. Negative controls in
  every job: `.github/audit-fixtures/npm-vulnerable` (lodash 4.17.20) and a urllib3 1.24.1 pin. Allow-list
  `.github/pip-audit-allowlist.txt` (empty) with enforced expiry via `scripts/audit_allowlist.py` (5 unit tests). Dependabot
  watches `apps/pitch` too.
* Evidence: audit run 1 (`8e4cdd9`) success in all 4 jobs. Python control output "Found 13 known vulnerabilities in 1
  package" (urllib3 1.24.1, PYSEC-2019-133 …); **first Python production audit ever: "No known vulnerabilities found"**; dev
  set also clean. npm controls rejected lodash in all three matrix jobs; production audits clean. ci run 89 on `8e4cdd9` success.
* Hardening after reading run 1: a control that only checked "non-zero exit" would also accept a crashing tool, so each control
  now also requires the planted advisory id in the output (verified locally against real `npm audit` output and the CI pip-audit line).
* Not executed locally: pip-audit (sandbox refuses `uvx`); CI is the evidence.
* State file updated: yes.

### L-0023 · 2026-11-25 · H-28 fix; B-050 · status: H-28 done; B-050 implemented (CI pending)
* Commits: `db19947` (H-28) and the following commit (B-050, audit hardening, docs).
* H-28: see MASTER_HANDOFF §16. Reproduction (scratch spec, deleted): hold the `/lab` chunk, clear cookies, click, dispatch
  `visibilitychange` → `/login?reason=expired` every run. Fix in `RequireAuth` (`window.location`). Regression test fails 3/3
  without the fix. Stress: both expiry tests `--repeat-each 30 --workers 4` → 59/60 at first (the new test lacked the API
  parking its neighbour has: "element was detached from the DOM"), after adding it **60/60**. Full Playwright cold cache
  **38 passed**; vitest 135; tsc clean; vite build ok.
* B-050: `apps/web/smoke/gestures.spec.ts` + `gestures` project in `playwright.smoke.config.ts` (fake camera flags). Tests:
  gateway serves `/vendor/mediapipe/*.wasm` as `application/wasm` with the same CSP as the shell, CSP has
  `'wasm-unsafe-eval'`, `worker-src 'self'`, `connect-src 'self'` and no `'unsafe-eval'`, `Permissions-Policy camera=(self)`,
  model > 1 MB and not HTML, missing vendor file 404; recogniser starts on the fake camera through the gateway, 1 live track,
  then 0, no foreign request, no console error; **negative control** strips `'wasm-unsafe-eval'` from every non-API response
  and expects the engine error, 0 live tracks, a CSP console error, and mouse/keyboard still working. No workflow change: the
  `containers` job already runs every project of the smoke config against the production images.
* Local verification (not the real Nginx): E2E API + worker (`scripts/e2e_stack.sh 8110`) behind
  `docs/handoff/probes/gateway_sim.mjs` serving the production bundle with the generated headers → 3 passed. Mutation: leave
  the policy intact in the negative control → it fails ("Покажите руку в кадре" instead of the engine error).
* Not executed: the real Nginx image (no Docker daemon) — the next CI `containers` run is the acceptance evidence.
* State file updated: yes.

### L-0024 · 2026-11-25 · B-050 CI evidence; B-013 · status: B-050 done; B-013 verified (DONE after CI)
* B-050 evidence: ci run 90 on `27ac946`, job "Production images + gateway smoke test" (real Nginx image, compose stack):
  "Running 7 tests using 1 worker" — desktop 3, mobile 1, **gestures 3 passed** (assets and policy 176 ms; recogniser on the fake
  camera 6.3 s; negative control 4.1 s); "7 passed (23.0s)". Audit run 2 on `27ac946` success (hardened controls).
* B-013: `apps/web` vite `^5.4.21` → `^8.3.8` (8.3.8, Rolldown), `@vitejs/plugin-react` `^4.7.0` → `^6.3.0`, vitest `^2.1.9` →
  `^5.1.0` (resolves 5.1.1). An exact `5.1.0` pin cannot be installed: npm's arborist crashes ("Cannot read properties of null
  (reading 'edgesOut')" in `#loadPeerSet`) because the newest optional peer `@vitest/browser-playwright@5.1.1` peers on vitest
  5.1.1; the caret range (repository convention) resolves cleanly. Lockfile regenerated from the original with only these changes;
  `npm ci` reproduces it. No source or config change was needed: `optimizeDeps.include`, `worker.format: "es"` and the
  `gestureAssets()` plugin work unchanged.
* Verification: `npm audit` (all deps) **0 vulnerabilities** (was 6: 2 critical, 1 high, 3 moderate); `npm audit --omit=dev` 0;
  `tsc -b` clean; vitest **135 passed**; `vite build` ok in 0.56 s (was 3.5 s) — landmark worker still a module worker
  (`{type: "module"}`) that lazy-imports the MediaPipe chunk, vendor assets copied; main chunk 336.6 kB / 105.0 kB gzip (was
  313.8 / 105.7). Playwright from a cold Vite cache **38 passed**, no "optimized dependencies changed / reloading" line in the
  output (the mid-session reload fixed in L-0001, `7abd9a5`, stays fixed); Playwright against the production bundle behind `gateway_sim.mjs` with the
  generated CSP **38 passed**.
* Not executed: Docker image build locally (CI `containers` job builds the gateway image with this toolchain).
* State file updated: yes.
