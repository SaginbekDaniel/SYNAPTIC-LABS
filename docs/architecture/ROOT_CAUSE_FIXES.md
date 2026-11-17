# Root-cause fixes

Each entry: reproduction → root cause → fix → regression test → measured consequence.

## RC-01 Contradictory date and timestamp accepted (F-03)

* **Reproduce**: `parse_record({..., "observed_date": "2026-07-10", "occurred_at": "2026-07-01T10:00:00Z"})`
  returned a `CanonicalRecord`.
* **Root cause**: `observed_date` and `occurred_at` were parsed independently; nothing checked that they
  describe the same moment. `chronological_order` uses the timestamp, `lag_days` uses the date.
* **Fix**: quarantine `DATE_TIMESTAMP_MISMATCH` when the UTC date of the timestamp differs from the
  posting date by more than one day (one day tolerated for time zones). `ingest/validation.py`.
* **Tests**: `test_observed_date_contradicting_timestamp_is_quarantined`,
  `test_one_day_timezone_offset_between_date_and_timestamp_is_accepted`.
* **Effect**: none on generated data (0 rows quarantined in dev and sealed); protects CSV imports.

## RC-02 Activation payments erase a funnel (F-02)

* **Reproduce**: five mules each receive 10 % from the centre, then send 10× that back; `detect_funnels`
  returned `[]`.
* **Root cause**: funnel-v2 treated a centre→sender payment ≥ 10 % of the sender's transfer as
  "funded by the centre" (loan repaid). A repayment cannot exceed its loan several times over, so the
  ratio had the wrong semantics for the evasion case and failed open.
* **Fix**: funnel-v3, `returning_min_ratio: 0.5` (repayment at most twice the disbursement). Real
  instalments (20–35 % of principal ⇒ ratio 3–5) are still excluded.
* **Tests**: `test_token_activation_payments_do_not_erase_a_collection_funnel`,
  `test_genuine_instalments_are_still_returning_feeders`.
* **Effect**: dev unchanged; sealed `SX2_activation_collection` 6/10 → 9/10 flagged, lending FPs 0/32
  in both.

## RC-03 Recurring business read as collection (F-01, F-04)

* **Reproduce**: `test_peer_counter_evidence_caps_band_with_named_gate` fixture (recurring customers,
  steady settlement) → v2 medium alert. Dev root-cause run: N7 treasury produced 58 funnel and 22
  fan-out alerts (medium/high), N2/N3 another 46.
* **Root cause**: the pipeline had a single suspicious reading per shape. Peer counter-evidence capped
  the band at medium but could not say *what else* explains the shape, and medium still alerts.
  Profiling on dev showed pass-through ratio does **not** separate the classes (merchant 0.98,
  treasury 0.91 vs fraud 0.80–0.92), while counterparty recurrence (≈0.9 vs 0.0) and activity span
  (≈1.0 vs 0.1–0.27) do — but each alone is evadable.
* **Fix**: hypothesis engine (`HYPOTHESIS_ENGINE.md`) and `risk-policy-v3` gate requiring two
  independent observation groups.
* **Tests**: `tests/unit/test_hypotheses.py` (8), integration
  `test_hypotheses_publish_with_resolvable_evidence_and_rerun_idempotently`, E2E `hypotheses.spec.ts`.
* **Effect**: dev FPR 0.467 → 0.242; sealed 0.507 → 0.159 with no suspicious family losing a detection.

## RC-04 Dataset selection race in the UI (F-10)

* **Reproduce**: create a dataset in the Lab while another exists, navigate to Overview → the previous
  dataset is shown. Full Playwright run: `redesign.spec.ts` overview test failed (0 alerts shown).
* **Root cause**: `DatasetProvider` called `setActiveId(new)` then `refresh()`; the fallback effect
  ran against the *stale* list, did not find the new id and replaced (and persisted) the selection.
* **Fix**: remember the list snapshot a selection was made against; skip the fallback until a newer list
  arrives. `apps/web/src/app/dataset.tsx`.
* **Test**: `e2e/hypotheses.spec.ts › a dataset created in the lab stays selected after navigation`
  (fails on the old code, passes on the new).

## RC-06 Commit after response (F-14)

* **Reproduce**: CI E2E runs failed intermittently with `DATASET_NOT_FOUND` right after the Lab created
  a dataset, and the dataset list refreshed without the new dataset. Locally (faster) never.
  Deterministic reproduction: `tests/integration/test_commit_before_response.py` drives the ASGI app
  and, when `http.response.start` is sent, counts datasets on an independent connection → 0.
* **Root cause**: `get_session` commits after `yield`; with FastAPI's default request scope that code
  runs after the response has been sent, so the client can observe a write before it is committed
  (and a failed commit would never reach the client).
* **Fix**: one `SessionDep` with `Depends(get_session, scope="function")` in `api/deps.py`, used by
  every route module (four duplicated definitions removed).
* **Diagnosis aid kept**: the E2E seed helper reports the API error text instead of a bare timeout;
  CI uploads Playwright results on failure.

## RC-05 Evaluation metrics and protocol (L-01, L-02, L-03, F-08, F-13)

* Distinct-network P@K, alerts per flagged network, abstention share, partial-analysis rate and
  quarantined formations in `benchmark.summarize`; invariants in `tests/unit/test_benchmark.py`.
* `sealed-gen-v1` with label-blind boundary and complete truth lists; exact `v2_shipped` baseline
  (config hash `489b477a3da5ac1b…` asserted); `v1_shipped` no longer inherits the engine.

## Failed or rejected experiments

| Experiment | Split | Result | Decision |
|---|---|---|---|
| Pass-through ratio as a benign test | dev | does not separate legitimate hubs from fraud | rejected before implementation |
| Gate `inconclusive → medium` | dev | identical metrics | not adopted (no unproven complexity) |
| Engine without peer statistics | dev / sealed | dev FPR 0.19 (better); sealed same FPR, high-band FPR 0.098 → 0.127 (worse) | not adopted; open question |
| Further tuning for N7 fan-out (one-off vendor payments) | dev | would fit the generator's vendor rule | deliberately not done; reported as `inconclusive` |
