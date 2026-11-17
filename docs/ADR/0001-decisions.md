# Architecture decisions (implemented subset)

Each entry: decision → consequence → exit criterion / rollback.

| ADR | Decision | Consequence | Exit / rollback |
|---|---|---|---|
| 001 | Modular monolith, one Python image for api/worker/migrate | Simple deploy, one lockfile | Split only with measured need |
| 002 | Postgres is the system of record; graph is a derived snapshot | Snapshot reproducible from `max_ingest_seq` + config | Recompute from ledger |
| 003 | Money = integer minor units (`NUMERIC(38,0)`, decimal strings in JSON); IDs = strings | No float drift; IDs > 2^53 survive JS | — |
| 004 | One typed `Evidence`/`Signal` contract for every detector | UI renders any detector generically | — |
| 005 | Priority is triage ranking 0–100, not probability | No "AI confidence" meter in UI | Calibrate only with labelled data |
| 006 | Chronology at the coarsest precision of a pair; equal day = ambiguous | No intraday claims from day data | — |
| 007 | Coverage limitations propagate; subject at boundary ⇒ abstain | Unresolved cases visible as `insufficient_evidence` | Policy list in `risk_policy.yaml` |
| 008 | Immutable transactions and snapshots; deterministic ids | Idempotent publish, late data ⇒ new snapshot | — |
| 009 | Synthetic labels never stored in runtime DB | Detectors cannot leak truth | — |
| 010 | Human decisions only; no enforcement API | Case actions write audit only | — |
| 011 | Batch snapshots per job, no per-event centrality | Bounded cost | Debounced incremental later |
| 012 | One React app, one OpenAPI-generated type file | No API/UI drift | `npm run gen:api` + diff in CI |
| 013 | No third-party code without verified licence | Independent implementation | See REFERENCE_AUDIT.md |
| 014 | No LLM in the evidence pipeline | Demo works offline | Optional narrator later, read-only |
