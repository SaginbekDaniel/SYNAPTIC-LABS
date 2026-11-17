# Implementation plan and gate status

| Stage | Scope | Status | Evidence |
|---|---|---|---|
| 0 Audit | Workspace + reference audit, contracts | **Done** (references not reachable — documented) | `REFERENCE_AUDIT.md`, `INTERFACES.md` |
| 1 Vertical slice | Ingest → DB → snapshot → detector → evidence → alert → API → React → case | **Done** | `docs/TEST_REPORT.md` |
| 2 Time/coverage | Strict vs ambiguous chronology, capacity flow, boundary abstention, NBDR | **Done for funnel+chain** | `tests/unit/test_temporal_flow.py`, `test_risk_and_pipeline.py` |
| 3 Risk + cases | Versioned policy, correlation guard, fingerprints, case state machine, audit | **Done (2 families)** | integration tests |
| 4 Evaluation | Frozen splits, baselines B0–B4, Precision@K, ablation, evaluation UI | **Next** | — |
| 5 UI | Overview, Alerts, Investigation, Network, Cases, Fraud Lab | **Done except Evaluation screen** | Playwright suite |
| 6 Reliability | Worker lease/retry ✔; durable replay, late events, peer statistics | **Partial** | `test_expired_lease_is_reclaimed` |
| 7 Release | Compose ✔, CI ✔, demo script, pitch, claims ledger | **Partial** | `docker-compose.yml`, `.github/workflows/ci.yml` |

## Next highest-value tasks (in order)

1. `scripts/run_benchmark.py`: frozen seeds per split, case-level matching rule fixed
   before measurement, baselines (volume, PageRank, static funnel rule, structure-only),
   confusion matrix by family/difficulty, Precision@K at analyst capacity K.
2. Hub counter-evidence on the **dev split only** (periodic settlement cadence, receiver
   fan-out) to address the N2 false positive; re-measure on held-out test.
3. Evaluation screen rendering the persisted benchmark artifact, labelled SYNTHETIC.
4. Replay runs with persisted cursor and late-event snapshots.
