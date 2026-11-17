# Adoption decisions

Each decision answers the spec §22 questions briefly. Rollback for every item is a configuration change
(`enabled: false` or the previous policy version), which also changes the config hash and therefore produces a
new snapshot without rewriting history.

## A1 — Fan-out detector (`fanout-v1`)
* **Problem:** coordinated distributions to mules were invisible when recipients did not forward (holdout v1:
  0/8 terminal distributions).
* **Source:** Vantage AI fan-out kind; AMLSim fan-out typology. Independent implementation.
* **Cost:** O(edges) per currency graph. **Verified by:** unit tests, holdout family table, ablation
  `minus_fan_out_cycle` (holdout recall 0.793 → 0.630 without it).

## A2 — Time-respecting cycle detector (`cycle-v1`)
* **Problem:** round-tripping was only caught when a chain happened to cover part of the loop.
* **Source:** Natural Intelligence, UNRU, AMLSim. Enumeration bounded by `length_bound` and `max_cycles`.
* **Correctness:** graph loops are only structural; the temporal engine decides (contradicted loops → `low`).

## A3 — Two-way relationship rule (funnel-v2, fan-out)
* **Problem (dev split):** every loan scenario (18/18) alerted *high*: borrowers repaying the lender looked like
  independent feeders; disbursements looked like dispersal.
* **Root cause, not a threshold:** funds returning to their origin are not consolidation of independent sources.
* **Effect (holdout ablation):** FPR 0.539 → 0.375, high-band FPR 0.227 → 0.062.
* **Known risk:** a launderer could add token repayments; `returning_min_ratio = 0.1` limits but does not remove
  this. Documented in `docs/LIMITATIONS.md`.

## A4 — Peer-statistics family (`peer-concentration-v1`) and risk-policy-v2
* **Problem:** steady business hubs (merchant settlement, treasury, suppliers) ranked *high*.
* **Source:** Natural Intelligence's cohort-relative fence; NEXORA cohort = activity-matched accounts with a
  labelled widening rule.
* **Policy:** counter-evidence caps at *medium* (still visible — spec §10.2 forbids auto-clearing).
* **Effect (holdout):** high-band FPR 0.281 (without peer) → 0.062; P@5 0.379 → 0.483; Recall@5 0.600 → 0.736.
* **Trade-off reported, not hidden:** peer corroboration raises family remittances (N5) into the queue, so
  any-alert FPR and F1 are slightly better *without* peer (B4: F1 0.702 vs 0.685).

## A5 — Benchmark harness, baselines, shadow evaluation
* **Source:** gen-fraud-graph (metric units), Handbook/SignalGraph (capacity framing), UNRU (perturbation),
  ezrules (shadow). Independent implementation, pure Python, no new dependencies (PageRank is a 20-line power
  iteration rather than adding NumPy/SciPy for a baseline).
