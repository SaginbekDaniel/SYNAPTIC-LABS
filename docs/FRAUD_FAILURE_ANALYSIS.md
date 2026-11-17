# Fraud failure analysis — engine `detectors-v1` / `risk-policy-v1`

Status: **Stage A baseline verification.** Every number below was reproduced in this session by
running the pure pipeline (`nexora.analytics.pipeline.run_analysis`) on the synthetic suite
`demo-v1`, seed `2026`, day precision — the same input the Fraud Lab button generates.
No threshold was changed before this analysis was written.

Reproduction: `uv run python scripts/trace_v1_false_positives.py` prints the full trace.
Golden fingerprint of the v1 output (70 risk assessments):
`051d7156022052580728a1d38f16dc4c138b21acf46565293f75db46c977277b`
(guarded by `tests/unit/test_v1_baseline_frozen.py`).

## 1. Claims verified

| Claim from the hand-over | Verified? | Observed |
|---|---|---|
| 64 backend tests pass | yes | `uv run pytest` → 64 passed (54 unit, 10 PostgreSQL) |
| 10 frontend tests pass | yes | `npx vitest run` → 10 passed; `npx tsc -b` clean |
| Merchant hub scores 64 vs fraud funnel 55 | yes | N2 processor `high`/64, S1 centre `high`/55 |
| A coincidental background chain reaches `high` | yes | one background 3-hop chain `high`/50 (ties the planted S2 chain) |
| No Precision/Recall benchmark exists | yes | `nexora.evaluation` contained only the scenario generator |
| CI verified on GitHub | **no** | workflow file exists; no run visible from this session |

## 2. Merchant-settlement hub ranked above the planted fraud funnel

### Score → signals

`risk-policy-v1` priority is `round(100 · Σ weight_f · strength_f)` over credited families.

| Formation | STRUCTURE strength | TEMPORAL strength | Priority | Band |
|---|---|---|---|---|
| N2 processor (legitimate) | 1.0000 (16 feeders) | 0.9541 (supported) | 0.35·1.0 + 0.30·0.9541 = **64** | high |
| S1 collection centre (planted fraud) | 0.8667 (5 feeders) | 0.8199 (supported) | 0.35·0.8667 + 0.30·0.8199 = **55** | high |

### Signals → observations

| Observation | N2 processor | S1 mule centre |
|---|---|---|
| Incoming transfers / outgoing transfers | 63 / 80 | 5 / 2 |
| Qualifying feeders | 16 | 5 |
| Transfers per qualifying feeder | 2–6 | 1 each |
| Feeders paying on ≥ 2 distinct days | **16 / 16** | 0 / 5 |
| Days with inflow | 26 of 30 | 3 (days 12–14) |
| Days with outflow | every 3rd day (3, 6, …, 30) | 1 (day 17) |
| Payouts per recipient | 10 to each of 8 merchants | 1 to each of 2 |
| Inflow ticket size (KZT) | 5 721 – 39 794 | 305 868 – 888 503 |
| Feeder share of own outflow | 0.56 – 0.92 | 1.00 for all |
| Chronology-compatible share of inflow | 95.4 % (lags 1–7 d) | 82.0 % (lags 3–5 d) |

### Root causes

1. **Structural strength rewards scale, not suspicion.** `funnel_strength` rises linearly from
   0.6 at 3 feeders to 1.0 at 6. A processor, biller or marketplace has *more* payers than a
   mule collector, so the heuristic orders the classes backwards. Feeder count was documented
   as "not proof" in `funnel.py`, but it is still the only input to the strength.
2. **The temporal family measures pass-through, which settlement does by design.** A processor
   that pays out 98 % every three days is chronology-compatible almost perfectly. Worse, with
   63 inflows and 80 outflows spread over the whole window, nearly every inflow has *some* later
   outflow within 7 days: the compatibility would be found whether or not any money is linked.
   The engine has no notion of how informative a "supported" result is for a continuously
   active account.
3. **No counter-evidence exists.** Facts that point to an operating business are observable in
   the transactions — every feeder pays repeatedly on different days, payouts follow a fixed
   cadence to the same recipients — but no detector computes them and the policy cannot use
   them. Spec §11.4 requires that "an ordinary payment processor shared by many merchants
   should remain explainable as a possibly benign hub"; v1 has no path to do that.
4. **Bands saturate.** With only STRUCTURE and TEMPORAL implemented, any funnel with ≥ 3 feeders
   and ≥ ~70 % compatible flow lands in `high`. Ranking inside `high` is then decided by root
   cause 1.

Changing `min_feeders` or the band thresholds would not fix any of these: the hub passes every
gate by a wide margin, and the planted funnel sits *below* it on the same scale.

## 3. Coincidental background chain reaching `high`

### Score → signals

| Formation | STRUCTURE | TEMPORAL | Priority | Band |
|---|---|---|---|---|
| Background path (no planted scenario account) | 0.6 (3 hops) | 0.9587 (supported) | 0.35·0.6 + 0.30·0.9587 = **50** | high |
| Planted S2 layering chain | 0.6 (3 hops) | 0.9602 (supported) | **50** | high |

The two are indistinguishable to the policy.

### Signals → observations

| Hop | Amount (KZT) | Transfers | Day |
|---|---|---|---|
| 0 | 103 935.64 | 1 | 12 |
| 1 | 103 439.74 | 1 | 15 |
| 2 | 99 652.40 | 2 | 18–19 |

| Intermediary | in/out counterparties | inflow / outflow (KZT) | path share of inflow | path share of outflow |
|---|---|---|---|---|
| #1 | 2 / 4 | 189 952 / 363 968 | 0.55 | **0.28** |
| #2 | 1 / 2 | 103 440 / 165 963 | 1.00 | 0.60 |
| planted S2 #1, #2 | 1 / 1 | — | 1.00 | 1.00 |

Population facts for the same dataset: 21 of 66 background accounts satisfy the v1
"pass-through intermediary" definition; the chain detector produced **67 candidates, 64 of
which touch no planted scenario**. Temporal verification rejected 61 of them.

### Root causes

1. **The intermediary role is satisfied by ordinary accounts.** v1 requires ≤ 4 counterparties
   each way and `min(in, out) / max(in, out) ≥ 0.5`. In a sparse graph most low-activity accounts
   qualify; intermediary #1 sent out 1.9× what it received and still passed.
2. **The path is not required to explain the intermediary's flow.** Only 28 % of intermediary
   #1's outflow leaves along the path. The structural evidence ("funds pass A→B→C→D") explains a
   minority of B's activity, yet is credited the same as a dedicated mule account.
3. **Multiple comparisons.** The candidate generator emits dozens of paths per dataset and the
   temporal test is effectively "are three single-transfer dates increasing with lags ≤ 7 d and
   amounts within 2×". Some random paths pass by chance; nothing discounts for the number of
   candidates tested or for coincidental amount similarity.
4. **Chain strength is a function of hop count only**, so it cannot express how much of the
   path is actually explained by dedicated pass-through behaviour.

## 4. Additional defects found while tracing

* **Duplicate credit across formations.** The 64 background chain candidates share
  transactions heavily (e.g. the same entry transfer appears in 6 distinct 5-hop chains). Each
  is assessed independently; the correlation guard only works *within* a formation.
* **Missing detector families.** Fan-out/distribution, circular-flow and split/re-consolidation
  patterns from spec §9.2/§9.4/§18.3 have no detector; any benchmark containing them will show
  zero recall for v1. That is a coverage gap, not a tuning problem.
* **`critical` is unreachable** (needs three supported families; only two exist).

## 5. What this analysis does *not* show

These are two cases from one seed. They demonstrate mechanisms, not rates. Rates are measured
by the labelled benchmark (`docs/EVALUATION.md`), whose baseline was recorded **before** any
detector change.
