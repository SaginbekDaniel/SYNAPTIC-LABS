# System architecture (diagrams)

Diagrams of the code on the default branch. Component details and invariants:
[ARCHITECTURE.md](../ARCHITECTURE.md). Deployment: [deployment/railway.md](../deployment/railway.md).

## Components and boundaries

```mermaid
flowchart TB
  subgraph browser[Browser]
    ui["React + TypeScript SPA<br/>Overview · Review Queue · Investigation · Network · Cases · Fraud Lab · Evaluation"]
  end
  subgraph gateway["Gateway (Nginx)"]
    gw["static SPA · /api proxy · access control · CSP · rate limits"]
  end
  subgraph python["Python (one image)"]
    api["nexora.api<br/>FastAPI routes, DTOs, error envelope"]
    worker["nexora.worker<br/>lease-based job runner"]
    app["nexora.application<br/>ingest · analysis jobs/publish · cases · read models"]
    analytics["nexora.analytics<br/>graph · detectors · temporal flow · peer stats · coverage · risk"]
    domain["nexora.domain<br/>money · transfers · chronology · typed contracts"]
    persistence["nexora.persistence<br/>SQLAlchemy models"]
  end
  db[("PostgreSQL")]
  ui -->|same-origin /api/v1| gw --> api
  api --> app
  worker --> app
  app --> analytics --> domain
  app --> persistence --> db
```

`nexora.domain` and `nexora.analytics` import no web or database framework, so the analysis
pipeline is pure and deterministic and the benchmark runs it without a database.

## Data ingestion

```mermaid
flowchart LR
  csv["CSV upload<br/>(≤ 20 MiB, ≤ 200 000 rows)"] --> adapter[csv_adapter<br/>schema, encoding]
  lab["Fraud Lab generator<br/>(synthetic, labels kept separately)"] --> validate
  adapter --> validate["row validation<br/>integer minor units · string ids · date vs timestamp precision"]
  validate -->|invalid rows| quarantine[(quarantine + report)]
  validate -->|valid| dedup["dedup by<br/>(dataset, source, source_tx_id)"]
  dedup --> tx[(transactions<br/>NUMERIC 38,0)]
```

Re-importing the same file is idempotent. Synthetic ground-truth labels never enter the
runtime database or detector input.

## Analysis job and evidence pipeline

```mermaid
sequenceDiagram
  participant UI
  participant API
  participant DB as PostgreSQL
  participant W as Worker
  UI->>API: POST /api/v1/analysis/jobs
  API->>DB: insert job (queued)
  W->>DB: claim (FOR UPDATE SKIP LOCKED), lease + heartbeat
  W->>DB: load transfers (no transaction held during compute)
  Note over W: snapshot → structural detectors → temporal max-flow<br/>→ peer statistics → coverage → evidence validation → risk policy
  W->>DB: re-check lease, publish snapshot/formations/evidence/alerts atomically
  UI->>API: poll job → succeeded
  UI->>API: GET alerts, evidence chain, neighbourhood
```

Ids are content-derived (UUIDv5), so re-running a job publishes nothing new. Evidence that does
not recompute from its cited transactions is quarantined, never published. Failures retry up to
`NEXORA_JOB_MAX_ATTEMPTS`, then the job is `failed` with an error code.

## Investigation lifecycle

```mermaid
stateDiagram-v2
  [*] --> new: analyst opens a case on an alert
  new --> investigating: take into work
  investigating --> escalated: escalate (reason)
  investigating --> dismissed: reject hypothesis (reason)
  investigating --> closed: close (reason)
  escalated --> closed: close (reason)
  dismissed --> closed: close (reason)
  closed --> reopened: reopen (reason)
  reopened --> investigating
```

Every transition and note is an append-only audit event in the same SQL transaction (a database
trigger rejects UPDATE/DELETE on `audit_events`), with optimistic concurrency on the case version.

Decisions are recorded for a human analyst; NEXORA takes no action against customers.
Exact state names and allowed transitions: `src/nexora/application/case_service.py`.
