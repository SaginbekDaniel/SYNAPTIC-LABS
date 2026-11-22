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
