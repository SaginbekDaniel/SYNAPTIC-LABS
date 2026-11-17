# Test report — Stage 0–3 vertical slice

- Date (UTC): 2026-11-17
- Host: Linux container, 4 vCPU, 15 GB RAM
- Python 3.13.18 · Node 22.23.4 · PostgreSQL 16.15 (local) and postgres:16-alpine (compose) · Chromium via Playwright 1.63.0
- Policy/config: `detectors-v1`, `risk-policy-v1` (hash recorded in every snapshot)
- Data: synthetic only (`synthetic-gen-v1`)

## Gates (all executed in this session)

| Gate | Command | Result |
|---|---|---|
| Python lint | `uv run ruff check src tests migrations scripts` | PASS |
| Python format | `uv run ruff format --check …` | PASS (56 files) |
| Python types | `uv run mypy` | PASS (44 source files) |
| Migration ↔ ORM parity | `uv run alembic check` | PASS (no drift); upgrade → downgrade → upgrade also verified |
| Python unit + integration | `uv run pytest` | **64 passed** (54 unit, 10 PostgreSQL integration) |
| Web types | `npx tsc -b` (strict, noUncheckedIndexedAccess) | PASS |
| Web unit | `npx vitest run` | **10 passed** |
| Web build | `npx vite build` | PASS (initial JS 209 kB / 69 kB gzip; Cytoscape lazy-loaded) |
| Browser E2E | `npx playwright test` (real API + worker + Postgres) | **5 passed** |

## Acceptance-matrix coverage (spec §21)

| IDs | Test |
|---|---|
| DATA-001 | `test_account_ids_are_kept_as_exact_strings`, `test_big_account_ids_round_trip_exactly` (API), `format.test.ts` |
| DATA-002 | `test_amount_keeps_values_beyond_js_safe_integer`, NUMERIC sum check in `test_reimport_is_idempotent…` |
| DATA-003 | `test_manifest_is_order_independent`, `test_pipeline_is_deterministic_under_row_reordering` |
| DATA-004/005 | `test_batch_duplicates_and_conflicts`, `test_reimport_is_idempotent_and_conflicts_quarantined` |
| DATA-006/007 | `test_day_precision_has_no_timestamp`, `test_currency_validation`, temporal `lag_seconds` is None for day data |
| GRAPH-001…004 | `test_aggregate_conservation_and_policy`, `test_direction_reversal…`, `test_self_transfer_only_account_is_an_isolate`, `test_chain_budget_fails_closed` |
| FORM-001…003 | `test_funnel_three_feeders`, demo-suite payroll assertion, reverse-chronology chain ⇒ low |
| TEMP-001…005 | `tests/unit/test_temporal_flow.py` (11 tests incl. missing leg, currency mix, reversal, budget) |
| COVER-001 | `test_subject_at_boundary_abstains`, demo-suite boundary funnel ⇒ insufficient_evidence |
| EVID-001…003 | `test_all_published_evidence_resolves_and_recomputes`, `test_broken_evidence_is_rejected`, FK join check, API recompute in E2E test |
| RISK-001…004 | `tests/unit/test_risk_and_pipeline.py` |
| CASE-001…003 | `test_case_lifecycle_conflict_and_audit`, API 409 check, Playwright journey |
| JOB-001/002 | `test_expired_lease_is_reclaimed`, `test_analysis_publishes_once…`, `test_failed_job_retries_then_fails_visibly` |
| BENCH-001/002 | `test_generator_is_deterministic_and_label_free` |
| UI-001…004 | Playwright `journey.spec.ts`, `mobile.spec.ts` |
| SEC-001/002 | XSS note rendered as text (E2E, no dialog); `test_graph_limits_are_clamped` |
| Audit append-only | `test_audit_log_is_append_only` (UPDATE/DELETE/TRUNCATE rejected by trigger) |

## Runtime checks

* Full Docker Compose stack (postgres → migrate → api → worker → web/nginx) started healthy.
  In this sandbox, images were built with `docker build --network host` and CA-trusting local base
  images passed via the `PYTHON_IMAGE` / `NODE_IMAGE` build args (the sandbox proxy re-signs TLS);
  `docker compose up --build` from an unrestricted network was **not** executed here.
* Restart check: generated `demo-v1`/2026, analysed, opened a case, moved it to *investigating*, then
  `docker compose restart api worker postgres web`: 382 transactions, 6 alerts, case status and audit
  trail unchanged; re-requesting analysis returned the same idempotent job.
* Browser journey against the nginx production build: zero console errors; SPA deep links return 200.
* 390 px: `scrollWidth ≤ 390` on all screens (asserted in E2E).

## Not tested / not built

Benchmark metrics (Stage 4), durable replay, late-event snapshots, peer statistics — see `LIMITATIONS.md`.
