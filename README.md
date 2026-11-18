<div align="center">

# NEXORA AI

**Explainable financial-network intelligence for fraud and AML investigation**

Turns raw transfers into evidence-backed, time-consistent, coverage-aware network investigations —
and leaves the decision to a human analyst.

[![ci](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/actions/workflows/ci.yml/badge.svg)](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/actions/workflows/ci.yml)
![Python 3.12–3.13](https://img.shields.io/badge/python-3.12%20%7C%203.13-3776AB)
![TypeScript](https://img.shields.io/badge/TypeScript-5.9-3178C6)

SYNAPTIC LABS · ITU Hackathon 2026 (Bank CenterCredit case) · prototype

</div>

> [!IMPORTANT]
> **Synthetic data only — no banking integration.** NEXORA is not connected to Bank CenterCredit or
> any bank, holds no customer data, and blocks nothing. A priority is a triage order, not a
> probability of fraud, and a detected pattern is not proof of wrongdoing.

![Investigation of a collection funnel: formation graph, priority and the reasons behind it](docs/assets/screenshots/investigation.webp)

## Why NEXORA exists

Transaction monitoring rules look at one transfer or one account at a time. Money-mule and
layering schemes are built to pass those checks: many small, individually ordinary transfers that
only look wrong **together** — five accounts feeding one collector, a chain of pass-through hops,
a loop that returns to its start.

Graph tools find such shapes easily — and drown analysts in them, because payroll, merchant
settlement and treasury sweeps have the same shapes. NEXORA's job is the part between "a shape
exists" and "an analyst should look at this first":

* Is the **chronology** consistent — could money received actually have funded what was sent on,
  given the dates and amounts?
* Is the account **unusual against its peers**, or typical for its activity level?
* What **could the system not see** — dates without times, an account at the edge of the data?
* Which **source transactions** prove each claim, so the analyst can verify instead of trust?

## Product tour

| | |
|---|---|
| ![Overview](docs/assets/screenshots/overview.webp) | ![Review Queue](docs/assets/screenshots/review-queue.webp) |
| **Overview** — what needs attention, by priority band, with transfer activity. | **Review Queue** — server-side paging, search by any member account, preview before opening. |
| ![Evaluation](docs/assets/screenshots/evaluation.webp) | ![Fraud Lab](docs/assets/screenshots/fraud-lab.webp) |
| **Evaluation** — the committed benchmark run, every split, against simple baselines. | **Fraud Lab** — generate a synthetic scenario suite and run the real worker on it. |

<details>
<summary>Light theme and 390 px mobile</summary>

<img src="docs/assets/screenshots/review-queue-light.webp" alt="Review Queue in the light theme" width="720"> <img src="docs/assets/screenshots/mobile-investigation.webp" alt="Investigation on a 390 px phone" width="240">

</details>

Screenshots are captured from the production build (`docker compose`) on a synthetic `demo-v1`
dataset (seed 2026). The UI is in Russian, the jury's working language.

## Live demo

**https://web-production-4593b103.up.railway.app** — *Synthetic Data Only — No Banking Integration*

The demo opens on the NEXORA sign-in page. Analysts sign in with a **named account**; there are
no published or default credentials — accounts are created by an operator
(`python -m nexora.auth.cli create-user`, see [SECURITY.md](SECURITY.md)). After signing in, open
**Лаборатория** → *Сгенерировать набор* → *Запустить анализ* → *Перейти к алертам*. Every case
decision is attributed to the signed-in analyst. Datasets created by earlier visitors stay in the
database.

Deployment record, what was verified and what was not:
[docs/deployment/railway.md](docs/deployment/railway.md#deployment-record).

## Key features

| | |
|---|---|
| **Network detection** | Collection funnels, coordinated fan-out, layering chains and time-checked cycles over a directed transfer graph with exact integer money and string account ids (including ids > 2⁵³). |
| **Temporal verification** | Capacity-constrained max-flow over dated transfers: *supported*, *possible but ambiguous* (same day), or *contradicted* (money sent before it arrived). |
| **Peer statistics** | Turnover concentration against an activity-matched cohort — corroboration **or** counter-evidence. |
| **Coverage awareness** | Abstains with `insufficient_evidence` at data boundaries and says which data would decide it. |
| **Risk prioritisation** | Versioned policy (`risk-policy-v2`): at most one credit per signal family, named evidence gates; legitimate-looking hubs are capped, never silently cleared. |
| **Evidence provenance** | Every claim links to the source transactions it recomputes from; evidence that does not recompute is quarantined, not shown. |
| **Investigation & cases** | Queue → hypothesis → reasons → highlighted transfers → formation graph → case decision with optimistic concurrency. |
| **Audit** | Append-only audit trail enforced by a PostgreSQL trigger. |
| **Reproducible evaluation** | Deterministic synthetic benchmark with frozen splits, baselines, ablations and robustness checks. |

## How it works

```mermaid
flowchart LR
  A["Transfers<br/>CSV or synthetic Lab"] --> B["Validate & dedup<br/>integer money · date vs time precision"]
  B --> C[("PostgreSQL")]
  C --> D["Worker job<br/>lease · heartbeat · retry"]
  D --> E["Graph snapshot"]
  E --> F["Structural detectors<br/>funnel · fan-out · chain · cycle"]
  F --> G["Temporal max-flow<br/>+ peer statistics<br/>+ coverage"]
  G --> H["Evidence validation<br/>recompute from source rows"]
  H --> I["Risk policy<br/>bands · gates · abstention"]
  I --> C
  C --> J["Review Queue → Investigation → Case decision + audit"]
```

The analysis pipeline (`nexora.analytics`) is pure and deterministic: no web or database
framework, content-derived ids, so re-running an analysis changes nothing. The worker computes
outside any database transaction and publishes atomically after re-checking its lease.
No LLM is involved anywhere in the evidence pipeline.

More: [architecture diagrams](docs/architecture/system.md) · [architecture and invariants](docs/ARCHITECTURE.md) · [interfaces](docs/INTERFACES.md).

## Architecture

| Layer | Technology |
|---|---|
| Web | React 18, TypeScript, Vite, Cytoscape.js; served by an unprivileged Nginx gateway |
| API | FastAPI, Pydantic v2 — typed DTOs, uniform error envelope, OpenAPI-generated TypeScript client |
| Analysis | Python 3.13, NetworkX, exact integer arithmetic |
| Jobs | PostgreSQL-backed lease worker (`FOR UPDATE SKIP LOCKED`), at-least-once with idempotent publish |
| Storage | PostgreSQL 16 via SQLAlchemy 2 + Alembic; `NUMERIC(38,0)` money, FK-enforced evidence links |
| Delivery | Docker, Docker Compose, GitHub Actions, Railway (Infrastructure as Code) |

## Evaluation

All measurements are on **synthetic data generated by the same team that wrote the detectors**.
They show behaviour on our scenarios, not accuracy on real bank data.

Benchmark `bench-v1`, holdout split (30 datasets), from the committed artifact
[`benchmarks/results/bench-v1.json`](benchmarks/results/bench-v1.json):

| | NEXORA v1 | NEXORA v2 | Best simple baseline |
|---|---:|---:|---|
| Planted suspicious networks flagged (scenario recall) | 60.9 % | 79.4 % | monitoring rules: 95.7 %, at 42.6 alerts per dataset |
| Legitimate networks reaching *high* priority | 43.8 % | 6.3 % | — (baselines have no bands) |
| Planted fraud among the first 5 alerts (P@5) | 31.3 % | 48.3 % | turnover ranking: 34.0 % |
| Planted networks found in the first 5 alerts (Recall@5) | 45.8 % | 73.6 % | monitoring rules: 43.6 % |

> [!WARNING]
> A later audit (open [PR #3](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/pull/3), not merged)
> found that these numbers are **optimistic**: the `bench-v1` holdout had been read during v2
> development; every boundary abstention in `bench-v1` was planted fraud (a label leak); and P@K
> counts duplicate alerts on one network. PR #3 adds a separately written, sealed evaluation with a
> pre-registered protocol. Its numbers come from a different generator and protocol and must not be
> compared with the table above.

Full tables, negative results and error examples: [docs/EVALUATION.md](docs/EVALUATION.md).
What does not work: [docs/LIMITATIONS.md](docs/LIMITATIONS.md). Reproduce:

```bash
uv run python scripts/run_benchmark.py
```

## Quick start

Requires Docker with Compose v2.

```bash
docker compose up --build -d --wait
```

Open http://127.0.0.1:8080 → **Лаборатория** → *Сгенерировать набор* → *Запустить анализ* →
*Перейти к алертам*. Everything binds to `127.0.0.1`.

Development servers with hot reload, test databases and troubleshooting:
[docs/development/local-setup.md](docs/development/local-setup.md).

## Cloud deployment

One public HTTPS entry point (the gateway); API, worker and PostgreSQL stay on Railway's private
network. Access control fails closed, migrations run once per deploy before the new API serves,
and deploys are manual, approval-gated and limited to commits with green CI.

```bash
scripts/railway/bootstrap.sh
```

Guide, security model, costs and rollback: [docs/deployment/railway.md](docs/deployment/railway.md).

## Development

```bash
make setup
```

```bash
make check
```

`make help` lists every target; each runs exactly the command CI runs. Testing strategy:
[docs/development/testing.md](docs/development/testing.md). Contribution rules:
[CONTRIBUTING.md](CONTRIBUTING.md).

## Documentation

| | |
|---|---|
| [docs/README.md](docs/README.md) | Index of all documentation |
| [Architecture diagrams](docs/architecture/system.md) · [ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, data flow, job processing, case lifecycle, invariants |
| [Railway deployment](docs/deployment/railway.md) | Topology, setup, variables, security, operations, cost |
| [EVALUATION.md](docs/EVALUATION.md) · [LIMITATIONS.md](docs/LIMITATIONS.md) | Benchmark results and honest scope |
| [Design](docs/design/DESIGN_DIRECTION.md) · [Research](docs/research/GITHUB_LANDSCAPE.md) · [ADRs](docs/ADR/0001-decisions.md) | Design system, prior-art research, decisions |

## Security

Analysts sign in with named accounts (Argon2id password hashes, server-side sessions in PostgreSQL,
HttpOnly `SameSite=Strict` cookies, CSRF and origin checks, brute-force throttling); the API rejects
every unauthenticated request and audit events carry the session's identity. There is no SSO, MFA or
role model, and it is a hackathon deployment, not a bank-grade system. See [SECURITY.md](SECURITY.md) for the controls
in place, the known gaps, and how to report a vulnerability privately.

## Roadmap

| Status | Item |
|---|---|
| Done | Ingest, four structural detectors, temporal flow, peer statistics, coverage, risk policy v2, investigation UI, cases and audit, `bench-v1` |
| Done | Production images, fail-closed gateway, Railway IaC, CI with production-image smoke test |
| Done | Named analyst accounts, server-side sessions, NEXORA sign-in page (replaces the shared Basic prompt) |
| In review | [PR #3](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/pull/3): competing-hypothesis engine, evaluation leakage fixes, sealed evaluation |
| Done | Protected Railway demo (PostgreSQL, API, worker, gateway); see the deployment record |
| Planned | Correlate alerts sharing a subject account; bridge/coordinator detector; named users via an identity-aware proxy |

## Contributing

Issues and pull requests are welcome — read [CONTRIBUTING.md](CONTRIBUTING.md) first (money is
integer minor units, ids are opaque strings, no synthetic labels in the runtime path).

## License

No license has been chosen yet, so default copyright applies: the code is published for review,
not licensed for reuse. The maintainers will add a `LICENSE` file when they decide.

## Acknowledgements

Built by SYNAPTIC LABS for the ITU Hackathon 2026 Bank CenterCredit case. Uses open-source work
including FastAPI, SQLAlchemy, Alembic, NetworkX, React, Vite and Cytoscape.js; third-party
licences are reviewed in [docs/research/LICENSE_MATRIX.md](docs/research/LICENSE_MATRIX.md).
