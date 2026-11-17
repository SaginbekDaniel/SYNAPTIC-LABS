# Architecture

Modular monolith + PostgreSQL + durable DB-backed worker + one React/TypeScript app (ADR-001).

```
CSV upload / synthetic generator
        │  (row validation, quarantine, dedup by (dataset, source, source_tx_id))
        ▼
FastAPI ──► PostgreSQL ◄── analysis_jobs (lease, heartbeat, bounded retry)
                │                    │
                │              Worker: load inputs → pure pipeline → atomic publish
                ▼
   snapshot · formations · evidence(+FK links to transactions) · signals · risk · alerts
                │
                ▼
     React (Alerts · Investigation · Network · Cases · Fraud Lab · Overview)
                │
                ▼
        Human decision + append-only audit (same SQL transaction)
```

## Packages and dependency rules

| Package | Responsibility | May import |
|---|---|---|
| `nexora.domain` | Money, transfers, chronology, ids, typed result contracts | stdlib only |
| `nexora.ingest` | CSV adapter, row validation, in-batch dedup | domain |
| `nexora.analytics` | Graph snapshot, structural + temporal detectors, coverage, risk, evidence checks, pipeline | domain, networkx, yaml |
| `nexora.evaluation` | Synthetic scenario generator (labels returned separately) | domain |
| `nexora.persistence` | SQLAlchemy models, engine/session | sqlalchemy |
| `nexora.application` | Use cases: ingest, analysis jobs/publish, cases, read models | all of the above |
| `nexora.api` | HTTP DTOs, routes, error envelope | application |
| `nexora.worker` | Lease-based job runner | application |

`analytics` never imports FastAPI or SQLAlchemy; `domain` imports nothing framework-specific.

## Analysis pipeline (pure, deterministic)

1. **Snapshot** (`graph_builder`): one aggregate edge per ordered pair+currency from
   `posted` transfers only; self-transfers counted per node, never edges.
   Input manifest hash is order-independent.
2. **Structural** detectors: `funnel` (≥3 feeders each routing ≥50 % of observed outflow to
   one centre) and `chain` (bounded path enumeration through low-degree pass-through
   intermediaries with consistent hop volumes; fails closed with `path_budget_exceeded`).
3. **Temporal** engine (`temporal/flow`): node-split max-flow over transfer layers with exact
   integer capacities. *Strict* links require provable order at the pair's precision;
   *possible* links add same-day/identical-instant pairs. Status: supported /
   possible_ambiguous / contradicted / unavailable.
4. **Coverage**: co-occurring limitations (day precision, boundary, downstream unobserved,
   upstream unknown, missing context) and next-best-data requests.
5. **Evidence** validation: every id resolves, sums recompute, no NaN — failures are
   quarantined, never published.
6. **Risk** (`risk-policy-v1`): ≤1 credited signal per family; missing families count zero
   (no renormalisation); evidence caps; subject at boundary ⇒ `insufficient_evidence`
   with no numeric priority.

All ids (snapshot, formation, evidence, signal, risk) are UUIDv5 of content, so reruns are
idempotent and row order never changes results.

## Persistence guarantees enforced by PostgreSQL

* `transactions`: `NUMERIC(38,0)` money, `amount_minor > 0`, precision/timestamp
  consistency CHECK, `UNIQUE(dataset_id, source_id, source_transaction_id)`.
* `evidence_transactions` FK → `transactions`: published evidence cannot reference a
  missing transaction.
* `graph_snapshots UNIQUE(dataset_id, input_manifest_sha256, config_sha256)`.
* `alerts UNIQUE(dataset_id, fingerprint)` — reruns update `last_seen`/revision, never duplicate.
* `audit_events`: statement trigger rejects UPDATE/DELETE/TRUNCATE.
* `risk_assessments` CHECK: `insufficient_evidence ⇔ priority IS NULL`.

## Worker semantics

At-least-once processing with idempotent effects (not exactly-once). Claim with
`FOR UPDATE SKIP LOCKED`, compute with no open transaction, publish after re-checking
lease ownership, heartbeat extends the lease, expired leases are reclaimable, failures
retry up to `job_max_attempts` then become `failed` with an error code.

## ADR index

See `docs/ADR/0001-decisions.md` (ADR-001 … ADR-014 as implemented in this slice).
