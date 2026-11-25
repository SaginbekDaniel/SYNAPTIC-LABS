# Dependency map

Task dependencies for [`EXECUTION_BACKLOG.md`](EXECUTION_BACKLOG.md). The diagram is **generated** from each task's
`Depends on` and `Status` lines — regenerate it, never edit it by hand:

```bash
python3 docs/handoff/probes/progress.py --mermaid   # paste between the markers below
```

`tests/unit/test_progress_probe.py` fails when the block below differs from the generated one. Arrows point from
prerequisite to dependent task. Colours: green DONE, red BLOCKED (owner, hardware or decision), grey TODO, amber in
progress / implemented, blue verified. A thick yellow border marks the critical path.

<!-- generated:mermaid:start -->
```mermaid
flowchart LR
  B001["B-001 P0"]:::done
  B002["B-002 P0"]:::blocked
  B003["B-003 P0"]:::done
  B004["B-004 P1"]:::verified
  B005["B-005 P1"]:::blocked
  B010["B-010 P0"]:::done
  B011["B-011 P1"]:::done
  B012["B-012 P1"]:::done
  B013["B-013 P1"]:::todo
  B014["B-014 P1"]:::implemented
  B015["B-015 P1"]:::done
  B016["B-016 P2"]:::todo
  B017["B-017 P2"]:::todo
  B018["B-018 P2"]:::todo
  B019["B-019 P2"]:::blocked
  B020["B-020 P1"]:::done
  B021["B-021 P2"]:::todo
  B022["B-022 P2"]:::todo
  B023["B-023 P2"]:::todo
  B024["B-024 P3"]:::todo
  B025["B-025 P2"]:::todo
  B030["B-030 P0"]:::blocked
  B031["B-031 P1"]:::done
  B032["B-032 P2"]:::todo
  B033["B-033 P2"]:::todo
  B040["B-040 P0"]:::done
  B041["B-041 P1"]:::done
  B042["B-042 P1"]:::todo
  B043["B-043 P2"]:::todo
  B044["B-044 P2"]:::todo
  B045["B-045 P2"]:::todo
  B046["B-046 P2"]:::todo
  B047["B-047 P2"]:::todo
  B048["B-048 P3"]:::blocked
  B050["B-050 P1"]:::todo
  B051["B-051 P1"]:::blocked
  B052["B-052 P1"]:::todo
  B053["B-053 P2"]:::todo
  B054["B-054 P3"]:::blocked
  B055["B-055 P1"]:::blocked
  B056["B-056 P1"]:::blocked
  B057["B-057 P2"]:::todo
  B001 --> B002
  B002 --> B003
  B003 --> B004
  B001 --> B011
  B010 --> B011
  B012 --> B013
  B012 --> B014
  B015 --> B016
  B011 --> B019
  B001 --> B021
  B022 --> B023
  B020 --> B024
  B021 --> B024
  B020 --> B025
  B031 --> B032
  B030 --> B033
  B003 --> B040
  B003 --> B041
  B041 --> B042
  B040 --> B043
  B041 --> B043
  B040 --> B044
  B040 --> B045
  B041 --> B046
  B041 --> B048
  B005 --> B051
  B002 --> B052
  B003 --> B052
  B004 --> B052
  B047 --> B054
  B001 --> B055
  B002 --> B055
  B005 --> B055
  B010 --> B055
  B012 --> B055
  B050 --> B055
  B002 --> B056
  B055 --> B057
  class B001,B002,B003,B004,B005,B010,B011,B012,B014,B030,B050,B052,B055 critical
  classDef done fill:#1f6f43,color:#fff,stroke:#1f6f43
  classDef blocked fill:#8a2b2b,color:#fff,stroke:#8a2b2b
  classDef todo fill:#3a3f4b,color:#fff,stroke:#3a3f4b
  classDef in_progress fill:#7a5a12,color:#fff,stroke:#7a5a12
  classDef implemented fill:#7a5a12,color:#fff,stroke:#7a5a12
  classDef verified fill:#2d5c7a,color:#fff,stroke:#2d5c7a
  classDef critical stroke:#f2c94c,stroke-width:4px
```
<!-- generated:mermaid:end -->

## Critical path to a release

A release (RELEASE_CHECKLIST.md) needs B-055, and B-055 needs B-001, B-002, B-005, B-010, B-012, B-050. Of those,
**B-002 and B-005 are owner-gated**, so the release is gated on the owner, not on engineering effort. The longest chain
of autonomous work on the path is **B-003 → B-004 → B-052** (documentation consolidation needs the reconciled numbers
and, by its own rule, the PR decision B-002). B-014 (dependency-audit gate) and B-050 (camera path through the real
gateway image) are independent of every other open task and can run now. B-030 (real webcam) blocks only the gesture claim
and B-033.

| Path segment | State (2026-11-25) | What unblocks it |
|---|---|---|
| B-001, B-003, B-010, B-011, B-012 | DONE | — |
| B-004 | ready | autonomous; merges `admiring-fermat` + `great-lovelace` |
| B-014, B-050 | ready | autonomous |
| B-002 | blocked | owner approves the integration PR and branch disposal (D-1, D-2) |
| B-005 | blocked | owner grants Railway workspace access |
| B-052 | waits | B-002, B-004 |
| B-055 | waits | owner approval after B-002, B-005, B-050 |
| B-030 | blocked | a person with a webcam runs `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` |

## Independent streams (safe to run in parallel)

| Stream | Ready tasks | Shared files to watch |
|---|---|---|
| Platform / supply chain | B-013, B-014, B-053 | `apps/web/package.json`, lockfile, `.github/workflows/ci.yml` — one upgrade per branch |
| Observability / reliability | B-016, B-017, B-047 | `src/nexora/worker/`, `src/nexora/api/deps.py` |
| Graph workspace | B-021, B-022, B-025 | `apps/web/src/features/graph/`, `src/nexora/application/graph_view.py` — serialise B-022/B-025 (same canvas) |
| Detection / evaluation | B-042, B-043, B-044, B-045, B-046 | `src/nexora/analytics/`; protocol rules §12 — never tune on sealed splits |
| Account self-service | B-018 | `src/nexora/auth/`, migrations (take the next free revision) |

**Integration order** when streams meet: migrations first (single head, B-001 guard), then API schema (regenerate the client
once), then UI. Two tasks that both add a migration must not land in the same CI window without a rebase.
