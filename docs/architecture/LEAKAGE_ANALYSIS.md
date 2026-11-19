# Leakage analysis

"Leakage" is used broadly: any path by which information unavailable in a real investigation, or
information from the evaluation itself, influences detection, scoring or reported quality.

## A. Target leakage

| Check | Method | Result |
|---|---|---|
| Labels in detector input | Generator rows have exactly the eight canonical fields (`test_bench_suite_is_deterministic_label_free_and_disjoint`, `test_sealed_split_is_disjoint_…`); ids are random, no role prefixes | Clean |
| Labels in the runtime DB | `create_synthetic_dataset` stores rows and the coverage contract only; grep for `truth`/`label` in `application`, `persistence`, `api`, `worker` | Clean |
| Labels via the **coverage contract** | Dev split: share of abstentions (`insufficient_evidence`) that are planted fraud | **Leak (L-01)**: 5/5 on dev, because `bench-v1` declares a boundary only on planted centres. Under the label-blind sealed contract the share is 0.31 |
| Thresholds selected with labels | All v3 engine thresholds are round values fixed in `configs/detectors.yaml` before evaluation; the only dev-driven choice was *not* adopting two variants | Documented in the protocol |

L-01 is not a runtime bug — a real boundary list comes from the data extract — but it made every
`bench-v1` metric that touches abstention optimistic. `bench-v1` is kept frozen so its published
numbers stay reproducible; new claims use `sealed-v1`.

## B. Train / validation / test contamination

* `bench-v1` dev, validation and holdout are seed ranges of **one** generator: they share mechanisms,
  amount distributions and timing models. A heuristic that fits that generator transfers for free.
* The `bench-v1` holdout results were read and published during v2 development. It is treated as
  exposed and was not used for any decision in this work.
* New: `sealed-gen-v1`, written separately, before the hypothesis engine (commit `b886a5f`, pushed),
  with different mechanisms, families that share every observable with fraud, adversarial fraud built
  against the planned features (recurring mules), complete truth lists and a label-blind boundary.
  Protocol, decision rule and file hashes were locked in that commit; one amendment before the run is
  recorded (A1). The sealed split was run once (`eece2de`); a later reproducibility re-run after a
  behaviour-preserving refactor produced identical results.
* Residual: the same team wrote detectors and both generators. Independence is procedural only.

## C. Temporal leakage

* The analysis input is bounded by the job watermark (`ingest_seq ≤ max_ingest_seq`); rows ingested
  later cannot reach an earlier snapshot.
* Same-day pairs are `ambiguous`, never ordered (unchanged; tested).
* **Found (F-03)**: a row could carry a timestamp and a contradictory date; ordering then used one and
  lags the other. Now quarantined.
* The engine's activity span and recurrence use every transfer in the snapshot, including transfers
  after the formation's own window. This is not look-ahead relative to the analysis time (the
  snapshot is an as-of view), but it means an alert raised early can be re-assessed when more history
  arrives — by design, as a new snapshot.

## D. Data and security leakage

See `DEEP_AUDIT.md` § Security. The material finding is F-05: no authorization or tenancy. Error
envelopes, logs and validation reports do not echo transaction payloads.

## E. Evidence leakage and contamination

| Risk | Status |
|---|---|
| Evidence of one formation attributed to another | Evidence ids are uuid5 of (formation, role); every hypothesis test cites ids that exist in the same formation's published evidence (unit + integration tests) |
| Transactions counted twice | Temporal flow refuses a transfer in two layers; aggregate evidence sums are re-validated (`validate_evidence`) |
| Shared observations treated as independent | Engine groups: concentration and activity span share `subject_activity` and count once (`test_dependent_observations_collapse_to_one_vote`) |
| Counter-evidence ignored | Benign verdicts gate the band explicitly with a named reason; assessments, evidence and hypotheses remain stored |
| Explanation not recomputable | New observations are `aggregate_fact` evidence with transaction ids and recomputable totals |

## F. Benchmark leakage

| Check | Result |
|---|---|
| Matching too permissive | Rule unchanged (subject in scenario, overlap ≥ min(2, item accounts)); a one-account partial overlap does not match (`test_single_shared_account_does_not_match_…`) |
| Duplicates inflate metrics | **Yes (L-02)** for raw P@K and alert precision. Distinct-network P@K added; sealed: raw P@5 0.713 vs distinct 0.593 for the candidate |
| Alert vs scenario confusion | Separate units, tested |
| Unlabelled background alerts | Count against alert precision, excluded from scenario FPR (tested); reported as `unmatched` |
