# Implementation plan and gate status

| Stage | Scope | Status | Evidence |
|---|---|---|---|
| 0 Audit | Workspace + reference audit, contracts | **Done** (references not reachable — documented) | `REFERENCE_AUDIT.md`, `INTERFACES.md` |
| 1 Vertical slice | Ingest → DB → snapshot → detector → evidence → alert → API → React → case | **Done** | `docs/TEST_REPORT.md` |
| 2 Time/coverage | Strict vs ambiguous chronology, capacity flow, boundary abstention, NBDR | **Done for funnel, fan-out, chain, cycle** | `tests/unit/test_temporal_flow.py`, `test_v2_detectors.py` |
| 3 Risk + cases | Versioned policy, correlation guard, fingerprints, case state machine, audit | **Done (3 families, risk-policy-v2)** | integration tests |
| 4 Evaluation | Frozen splits, baselines B0–B4, Precision@K, ablation, robustness, evaluation UI | **Done** | `docs/EVALUATION.md`, `tests/unit/test_benchmark.py`, `e2e/evaluation.spec.ts` |
| 5 UI | Overview, Alerts, Investigation, Network, Cases, Fraud Lab, Evaluation | **Done** | Playwright suite |
| 6 Reliability | Worker lease/retry ✔; durable replay, late events, peer statistics | **Partial** | `test_expired_lease_is_reclaimed` |
| 7 Release | Compose ✔, CI ✔, demo script, pitch, claims ledger | **Partial** | `docker-compose.yml`, `.github/workflows/ci.yml` |

## Next highest-value tasks (in order)

1. Correlate alerts that share a subject account (funnel + fan-out on one hub) into one review item.
2. Bridge/coordinator detector → NETWORK_CONTEXT family; re-measure on a *new* holdout seed range
   (the current holdout has now been used once).
3. Signal that separates family remittances from mule distributions (needs data beyond transfers, e.g.
   account type or relationship history) — measure on dev first.
4. Replay runs with persisted cursor and late-event snapshots.
