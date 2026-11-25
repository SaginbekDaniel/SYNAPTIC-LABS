# Project completion — document index

The completion protocol asks for a set of management documents. They already exist under
[`docs/handoff/`](../handoff/), maintained by every session since 2026-11-21; creating copies here would give two sources
of truth that drift. This page maps each requested document to the one file that holds it.

| Requested document | Single source of truth | Notes |
|---|---|---|
| `MASTER_PLAN.md` | [`MASTER_HANDOFF.md`](../handoff/MASTER_HANDOFF.md) §1–§3, §21, §23 + [`EXECUTION_BACKLOG.md`](../handoff/EXECUTION_BACKLOG.md) waves | current/target state, roadmap, Definition of Done |
| `TASK_CHECKLIST.md` | [`EXECUTION_BACKLOG.md`](../handoff/EXECUTION_BACKLOG.md) | atomic tasks with priority, dependencies, modules, acceptance, tests, a machine-read **Status** line and commit evidence |
| `CURRENT_STATE.md` | [`EXECUTION_STATE.md`](../handoff/EXECUTION_STATE.md) | branch, HEAD, completed/active/pending, blockers, latest results, next exact commands |
| `ARCHITECTURE_AUDIT.md` | [`MASTER_HANDOFF.md`](../handoff/MASTER_HANDOFF.md) §4–§14, §16 + [`docs/architecture/DEEP_AUDIT.md`](../architecture/DEEP_AUDIT.md) | per-component state, findings `H-nn` with evidence |
| `DEPENDENCY_MAP.md` | [`DEPENDENCY_MAP.md`](../handoff/DEPENDENCY_MAP.md) | Mermaid graph generated from the backlog; critical path; parallel streams |
| `RISK_REGISTER.md` | [`RISK_REGISTER.md`](../handoff/RISK_REGISTER.md) | |
| `DECISION_LOG.md` | [`docs/ADR/0001-decisions.md`](../ADR/0001-decisions.md) (made) + [`MASTER_HANDOFF.md`](../handoff/MASTER_HANDOFF.md) §19–§20 (made / open `D-n`) | |
| `TEST_MATRIX.md` | [`TEST_MATRIX.md`](../handoff/TEST_MATRIX.md) | |
| `RELEASE_CHECKLIST.md` | [`RELEASE_CHECKLIST.md`](../handoff/RELEASE_CHECKLIST.md) | |
| `SESSION_HANDOFF.md` | [`NEXT_SESSION_PROMPT.md`](../handoff/NEXT_SESSION_PROMPT.md) + [`EXECUTION_STATE.md`](../handoff/EXECUTION_STATE.md) | paste-ready prompt for a fresh session |
| `EXECUTION_LEDGER.md` | [`EXECUTION_LEDGER.md`](../handoff/EXECUTION_LEDGER.md) | append-only, literal command results |

## Completion progress

Computed, never typed:

```bash
python3 docs/handoff/probes/progress.py            # summary
python3 docs/handoff/probes/progress.py --markdown # table for EXECUTION_STATE.md
```

Formula: `sum(weights of DONE tasks) / sum(weights of all tasks) × 100`, weights P0 = 8, P1 = 5, P2 = 3, P3 = 1. A task counts
as DONE only with a reachable commit and an existing ledger entry (enforced by `tests/unit/test_progress_probe.py`). The
release gates in `RELEASE_CHECKLIST.md` apply regardless of the percentage.
