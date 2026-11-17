# Deep audit — issue register

Audit of the merged baseline `4c01a7a` (PR #2), November 2026. Branch `claude/quirky-ride-v565zk`.
Every finding below was reproduced before it was fixed; "fixed" means a regression test failed on the
old code and passes on the new code. Synthetic data only.

Companion documents: `LEAKAGE_ANALYSIS.md` (leakage classes), `ROOT_CAUSE_FIXES.md` (fix details),
`HYPOTHESIS_ENGINE.md` (new architecture), `../evaluation/EXPERIMENT_PROTOCOL.md` and
`../evaluation/RESULTS.md` (measurement).

## Baseline established (Stage A)

| Gate | Result at `4c01a7a` |
|---|---|
| `ruff check`, `ruff format --check`, `mypy` | clean |
| `pytest` (unit + PostgreSQL 16 integration) | 99 passed |
| `scripts/run_benchmark.py` | reproduces `benchmarks/results/bench-v1.json` exactly except wall-clock latency (verified field by field) |
| Playwright E2E | 10 passed in isolation order; see F-10 for a latent race |

## Severity scale

P0 data leakage / evidence corruption / financial correctness / security-critical · P1 major detection
mistake, unsafe conclusion, evaluation leakage, reliability failure · P2 architectural inconsistency,
duplicate work, performance · P3 cleanup.

## Register

| ID | Sev | Component | Finding | Status |
|---|---|---|---|---|
| L-01 | P1 | evaluation / generator | Coverage-contract **label leak**: `bench-v1` declares a collection boundary only on planted fraud centres, so every abstention is a true positive by construction | Fixed for new evaluation (label-blind boundary in `sealed-gen-v1`); `bench-v1` kept frozen and documented |
| L-02 | P1 | evaluation / harness | **Duplicate-alert inflation**: P@K and alert precision count every alert on one planted network | Fixed: distinct-network P@K, alerts per flagged network, tests |
| L-03 | P1 | evaluation / protocol | `bench-v1` holdout was read during v2 development; all three splits share one generator | Fixed: independent sealed generator, protocol locked and pushed before the engine existed |
| F-01 | P1 | detection / funnel | Recurring business revenue (customers paying a merchant, supplier or treasury company repeatedly) is read as a **collection funnel**; legitimate hubs stayed alerted at medium | Fixed by the hypothesis engine (verdict + policy gate), measured on sealed |
| F-02 | P1 | detection / funnel | **Fail-open evasion**: a 10 % token payment from the centre to each mule reclassified every feeder as "returning", erasing the funnel | Fixed (funnel-v3) |
| F-03 | P1 | ingestion | Rows whose `observed_date` contradicts their own `occurred_at` (e.g. 9 days apart) were **accepted**; ordering used the timestamp, lags the date | Fixed: `DATE_TIMESTAMP_MISMATCH` quarantine (1-day tolerance) |
| F-04 | P1 | decision / explanation | No representation of competing explanations; risk reasons could not say *which* legitimate activity shares the shape or *what data would decide* | Fixed: hypothesis registry, falsification tests, UI section |
| F-05 | P1 | security | **No authorization**: one demo identity; every client can read every dataset, alert, transaction and case | Open — out of scope for a demo; documented (not masked with superficial controls) |
| F-06 | P2 | detection / temporal | Slow accumulation (deposits over two weeks, forwarded after the last one) fails the 7-day lag and is capped low; recurring-mule collection is missed by both v2 and v3 (sealed: 1/8) | Open — documented false-negative mechanism; changing it needs a new sealed set |
| F-07 | P2 | detection / fan-out | A recipient that sends back ≥ 10 % of what it received is treated as a loan relationship; mule kickbacks of ≥ 10 % are indistinguishable from instalments by ratio alone | Open — documented; unlike F-02, ratio semantics cannot separate them |
| F-08 | P2 | evaluation / generator | `bench-v1` truth account lists omit some scenario accounts (N5 colleagues, N2 "others", N3 suppliers' other clients, N7 vendors); the `background_xN` perturbation can touch them | Fixed in `sealed-gen-v1` (complete lists, tested); `bench-v1` frozen |
| F-09 | P2 | persistence | Snapshot identity hashes input and config but not the coverage contract; harmless only because contracts are immutable after creation | Open, latent — documented |
| F-10 | P2 | frontend | **Dataset selection race**: after the Lab creates a dataset, the fallback effect runs against the stale list and silently replaces the fresh selection with the previous newest dataset (and persists that) | Fixed; E2E reproduces on the old code |
| F-11 | P2 | performance | New engine's activity observation scanned all edges per formation | Fixed before merge (index once per currency); outputs bit-identical |
| F-12 | P3 | risk policy | A `possible_ambiguous` temporal signal contributes 0.4 × weight to the score although it is not "supported" (band is capped at medium) | Open — documented; no measured harm |
| F-13 | P3 | harness | The new `v1_shipped` variant initially kept the hypothesis engine | Fixed before the sealed run; recorded as protocol amendment A1 |

## Assumptions attacked (Section 5 of the brief)

| Assumption | Code | Minimal counterexample | Observed | Outcome |
|---|---|---|---|---|
| Many incoming payments ⇒ collection funnel | `structural/funnel.py` | 6 customers paying a hub 5× over a month, hub settles every 3 days | v2: funnel, temporal supported, peer contradicted → **medium alert** | Root cause: recurrence and activity span never tested. v3 favours the recurring-business explanation → low (`test_peer_counter_evidence_caps_band_with_named_gate`, `test_recurring_business_favours_…`) |
| Rapid distribution ⇒ suspicious | `structural/fan_out.py` | salary arrives, worker sends 4–12 % each to 5 relatives within 2 days | v2 and v3 alert; peer and temporal both "support" | Indistinguishable on transactions alone; v3 lists `personal_remittance` as an **untestable** alternative with the data needed (KYC relationships, income source). Not hidden |
| Closed loop ⇒ same funds circulated | `structural/cycle.py` | — | Already guarded: temporal flow must close the loop in order; limitation `loop_does_not_prove_same_funds` | Kept |
| High concentration ⇒ fraud | `statistical/peer.py` | ticket sales: one-off buyers within days | Peer "supported" | Kept as one vote in the `subject_activity` group, never decisive alone |
| Stable merchant hub ⇒ legitimate | v3 engine | mules depositing twice each over two weeks (recurring) | v3: `recurring_business` gets 1 group only → **not** favoured (`test_recurrence_alone_cannot_clear_a_collection`) | Benign verdict needs two independent groups |
| Two-way relationship ⇒ loan repayment | `funnel.py` (`returning_min_ratio`) | centre pays each mule 10 %, then collects 10× | v2: funnel erased (F-02) | funnel-v3: repayment ≤ 2× disbursement |
| Correlated signals counted as independent | `risk.py`, peer + temporal | — | Measured on dev: peer and temporal disagree on 108 of 168 temporal-supported hub formations, so they are not redundant | No change to v2 scoring; in the engine, turnover concentration and activity span **share one group** because they read the same dates |

Metamorphic invariants (row order, account renaming, currency separation, evidence removal) were
tested and **already held** on the baseline — recorded as negative findings, kept as regression tests
(`tests/unit/test_audit_regressions.py`).

## Security review summary

| Area | Finding |
|---|---|
| Authorization / tenancy | None (F-05). Demo identity only; must not be presented as multi-tenant banking infrastructure |
| Error responses | Generic envelope with request id; no stack traces, SQL or input echoed (validation reports carry row numbers and codes only) |
| Logging | Worker logs job ids and exceptions; no transaction payloads. DB-unavailable logs the driver message (host/user, no password) |
| Injection | ORM-parameterised queries; alert search escapes `LIKE` metacharacters; CSV values are never evaluated; UI renders notes as text (existing XSS E2E) |
| Resource bounds | Upload 20 MB, 200 000 rows; path/cycle/flow budgets fail closed and mark the snapshot partial (sealed: 0 partial runs) |
| Cross-dataset references | Evidence links are FKs to transactions; snapshot reads are bounded by `dataset_id` and `ingest_seq`; new hypothesis evidence uses the same FK path (integration test) |
| CORS | Explicit allow-list, GET/POST only |
| Secrets | `.env.example` has no secrets; none in the diff (checked before push) |
