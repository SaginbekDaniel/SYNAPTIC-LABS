# Experiment protocol — sealed evaluation `sealed-v2`

Status: **LOCKED** (2026-11-23). This file is committed together with the generator, its tests and the runner
changes, and that commit precedes the commit that adds `benchmarks/results/sealed-v2-evaluation.json`
(verify with `git log --follow` on this file and on the artifact). No detector, policy or analysis was run on
`sealed-v2` data before this lock: the generator's tests check generator properties only. Changing anything below
after the run invalidates it.

## Why a second sealed split

`sealed-v1` (seeds 9000–9059, [`EXPERIMENT_PROTOCOL.md`](EXPERIMENT_PROTOCOL.md)) was evaluated once and is
**consumed**: judging any later detector or policy change on it would be selection on the test set (finding H-14).
The `bench-v1` splits are exposed. `sealed-v2` is the held-out set for later claims.

| Split | Seeds | Status |
|---|---|---|
| `bench-v1` dev / validation / holdout | 1000–1029 / 2000–2019 / 3000–3029 | exposed |
| `sealed-v1` | 9000–9059 | consumed (one run, amendment A2 re-derived metric arithmetic only) |
| `sealed-v2` | **9100–9179 (80 datasets)** | sealed until the single run below |

## Generator `sealed-gen-v2`

`src/nexora/evaluation/sealed_generator_v2.py`, sha256 at lock:
`a2a8dc7a89acff82cbdae84874cd582cf126c7897de4f0d508b024789ec9c31a`; split sha256 (data only):
`39652b9d88409bd46f99fc89c9222401599e594ad04ca9ab7f8110d7e6e684fc`.

* A separate file; `sealed_generator.py` (v1) is unchanged (sha256 `558e3595…446e073e9f`).
* 60-day window from 2026-05-04; log-normal amounts; business-hours timestamps and weekend shifts for ordinary
  commerce; changed parameter ranges for every typology v1 also has.
* 12 suspicious families, 3 of them new (two-tier collection through sub-collectors, scatter-gather structuring,
  salary-like pass-through mule); 13 legitimate families, 4 of them new (merchant with unobserved outflows, property
  escrow, payroll agency, group gift).
* **Label-blind boundaries**: a 5 % random sample of all accounts present in the data, drawn from a seed stream
  independent of scenario building, plus the centres of boundary scenarios of **both** labels (a suspicious
  collection and a legitimate merchant, each with unobserved outflows). v1 declared boundary centres for suspicious
  scenarios only.
* Truth lists contain exactly the accounts that occur in a scenario's transactions; scenarios never share accounts;
  ground truth never enters rows or the coverage contract (`tests/unit/test_sealed_generator_v2.py`, 10 tests). The
  same check on v1 found 4 of 1,740 suspicious truth accounts (and 45 legitimate ones, plus 9 declared boundary
  accounts) that never occur in any row; v1's published scenario-level results are unaffected (matching requires a
  transacting subject), and v1 is not re-run (consumed).

## Harness and runner

* `src/nexora/evaluation/benchmark.py` sha256 `ab6f162f0f30da5d42961494308ad13ef9e617a21c517831a22c6862f880d248`
  (matching rule unchanged since `bench-v1`: subject in scenario, overlap ≥ min(2, |item accounts|)).
* `src/nexora/evaluation/entity_metrics.py` sha256 `649060f972254ec2871788d9b8c9d5f839c9d62a8df0f1edb186af1111034abe`.
* `scripts/run_sealed_evaluation.py` sha256 `d707a5eaa68610c7ed103d30bfce0071ef430470d0b6e149c327eef154d3c852`;
  paired bootstrap 2,000 draws, seed 20261117 (as for v1); entity bootstrap 2,000 draws, seed 20261123.

## Methods

1. **Candidate** — the configuration at this lock: `detectors-v3` / `risk-policy-v3` (hypothesis engine
   `hypotheses-v1`), config sha256 `1f9e2a64aaa1d563ebe71efc9d5aa8207bbac7dc2405b450b8b19bcf460f1055`. It is the
   configuration already evaluated on `sealed-v1`; nothing was tuned after that run.
2. **Baseline** — `v2_shipped`, the configuration merged at `4c01a7a`, config sha256
   `489b477a3da5ac1bac8ae3a7e3c1f5f22d9aac2a826e966d04d700347f194153`.
3. Ablations and simple baselines (B0, B1, B3, `v1_shipped`) as in the runner, for context only.

## Pre-registered question and decision rule

**Question**: does the candidate's improvement over the baseline, reported on `sealed-v1`, **replicate** on an
independently generated split with new families and label-blind boundaries?

The rule is the one locked for `sealed-v1` (applied mechanically by `decide()` in the runner). The result is reported
as **replicated** only if all hold on `sealed-v2`:

1. scenario recall drops by at most 2 percentage points versus the baseline;
2. high-band FPR does not increase;
3. scenario FPR **or** distinct P@5 improves, with the paired bootstrap 95 % interval for that difference excluding
   zero.

Otherwise the result is reported as *not replicated*, with the numbers, and no claim of improvement is made.
Per-family results are reported regardless. Entity-level, ranking and band-reliability metrics (B-041) are
**descriptive** and not part of the rule.

## Procedure

1. Commit this protocol with the generator, tests and runner (the lock). No candidate has been run on `sealed-v2`.
2. On a clean tree at a later commit that changes none of the hashed files above, run once:
   `uv run python scripts/run_sealed_evaluation.py --split sealed_v2` and commit
   `benchmarks/results/sealed-v2-evaluation.json` unchanged.
3. Re-run once to check reproducibility: every field except latency, runtime, timestamp and commit must be
   identical (the outcome is recorded with the artifact commit).
4. A harness defect found after the run is documented as an amendment here, with a full re-run; the configuration
   may not change in response to `sealed-v2` results.

## Use after the run

* `sealed-v2` may then be used to evaluate **frozen** candidates developed on `bench-v1` dev only (backlog B-043,
  B-044, B-046): each candidate is frozen and committed first, evaluated once, and recorded as an amendment here with
  its commit and outcome.
* After **three** such evaluations, or as soon as any change is selected because of its `sealed-v2` result, the split
  is consumed and `sealed-v3` is needed.

## Known limits

* All data is synthetic. The numbers describe behaviour on generated scenarios, not accuracy on bank data.
* The same project wrote the detectors and both sealed generators. This generator was written by an author who had
  read the `sealed-v1` results and knows the detectors' documented weaknesses; independence is procedural (protocol
  locked before any run, no detector output consulted while writing it), not organisational. New families were
  chosen from typologies and legitimate lookalikes, not from detector behaviour on this split, which was never run.
* 80 datasets give wide intervals for rare families; per-family numbers are descriptive.
