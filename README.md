<div align="center">

# NEXORA

**Network investigation for bank anti-fraud and AML analysts.**<br>
NEXORA finds suspicious networks of transfers, checks whether time and context support them,<br>
and shows the analyst every source transaction behind each claim. The decision stays with a human.

[Live demo](https://web-production-4593b103.up.railway.app) ·
[Jury pitch](https://pitch-production-1554324d.up.railway.app) ·
[Benchmark](#evidence-a-reproducible-benchmark) ·
[Architecture](#architecture) ·
[Quick start](#quick-start) ·
[Docs](docs/README.md)

[![ci](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/actions/workflows/ci.yml/badge.svg)](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/actions/workflows/ci.yml)

<sub>SYNAPTIC LABS · ITU Hackathon 2026 (Bank CenterCredit case) · prototype on synthetic data, no bank integration</sub>

</div>

<br>

![Investigation of collection funnel ··7530: the formation graph, the reasons it is suspicious, and what the system does not know](docs/assets/screenshots/investigation.webp)

<p align="center"><sub>Investigation screen of the deployed prototype · synthetic <code>demo-v1</code> dataset</sub></p>

## The problem

Transaction monitoring rules score **one account at a time**: "five senders in three days", "pass-through
volume", "large amount". A money-mule collection funnel trips those rules — and so does a merchant receiving
card settlements, a payroll run or a treasury sweep, because at the account level they look the same.

So banks face a trade-off: tune rules to catch schemes and the queue fills with legitimate businesses; tune them
for a short queue and schemes slip through. Each alert reaches the analyst as an account, not as a story, and the
network around it has to be rebuilt by hand.

## How NEXORA works

NEXORA treats the **network**, not the account, as the unit of review, and asks three questions about it:

| | Question | Example from the screen above |
|---|---|---|
| **Structure** | Is there a funnel, fan-out, layering chain or cycle? This only says *where to look*. | 5 accounts → `··7530` → 2 accounts |
| **Chronology** | Could the money that came in have funded what went out, given dates and amounts? | 81.9 % of inflows are compatible with the outflow, 3–5 days later |
| **Peer context** | Is the account unusual against accounts with similar activity, or typical? | Above the median of 77 peers, but not an outlier — reported as a limit, not as evidence |

The result is a **priority for the review queue** (0–100), not a probability of fraud. When the data cannot
decide — dates without times, an account at the edge of the export — NEXORA says so and names the data that
would decide it.

```mermaid
flowchart TB
  subgraph ingest["1 · Ingest"]
    direction LR
    A["Transfers<br/>CSV or synthetic generator"] --> B["Validate<br/>integer money · dedup · quarantine"]
  end
  subgraph analyse["2 · Analyse (pure core)"]
    direction LR
    C["Graph snapshot"] --> D["Detectors<br/>funnel · fan-out<br/>chain · cycle"] --> E["Signals<br/>chronology · peers<br/>coverage"] --> F["Evidence check<br/>recomputes from<br/>source rows"] --> G["Risk policy<br/>bands · gates"]
  end
  subgraph review["3 · Review"]
    direction LR
    H["Queue by priority"] --> I["Analyst decision<br/>append-only audit"]
  end
  ingest --> analyse --> review
```

The pipeline (`nexora.analytics`) is pure and deterministic: no web or database framework, content-derived ids,
**no language model anywhere in the evidence path**, and no automatic action against a customer.

## The product

| | |
|---|---|
| ![Review queue: networks in review order with a preview](docs/assets/screenshots/review-queue.webp) | ![Overview: what needs attention, by priority band](docs/assets/screenshots/overview.webp) |
| **Review queue** — networks in review order; search by any member account; preview before opening. | **Overview** — what needs attention, by priority band, with transfer activity. |
| ![Evaluation: the committed benchmark run against baselines](docs/assets/screenshots/evaluation.webp) | ![Fraud Lab: generate a synthetic suite and run the real worker](docs/assets/screenshots/fraud-lab.webp) |
| **Evaluation** — the committed benchmark run, every split, against simple baselines. | **Fraud Lab** — generate a synthetic scenario suite and run the real worker on it. |

<details>
<summary>Light theme and 390 px mobile</summary>
<br>
<img src="docs/assets/screenshots/review-queue-light.webp" alt="Review queue in the light theme" width="640">
<img src="docs/assets/screenshots/mobile-investigation.webp" alt="Investigation on a 390 px phone" width="200">
</details>

**Try it.** The [live demo](https://web-production-4593b103.up.railway.app) is behind a shared login (ask the
maintainers; credentials are not published). Open **Лаборатория** → *Сгенерировать набор* → *Запустить анализ* →
*Перейти к алертам*. The UI is in Russian, the jury's working language. Everything is synthetic.

## Evidence: a reproducible benchmark

NEXORA against **per-account monitoring rules** (baseline B1: fan-in/out velocity, large amount, pass-through) on
the holdout split of `bench-v1` — 30 synthetic datasets with 220 planted networks (92 suspicious, 128 legitimate
look-alikes such as payroll, merchant settlement and treasury sweeps).

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/assets/readme/benchmark-dark.svg">
  <img alt="Alerts per dataset 42.6 vs 9.5; legitimate networks flagged 80.5 % vs 37.5 %; recall 95.7 % vs 79.3 %" src="docs/assets/readme/benchmark-light.svg" width="880">
</picture>

**The trade-off is real.** NEXORA's queue is 4.5× shorter and flags far fewer legitimate networks, but it finds
fewer planted schemes: 73 of 92 against the rules' 88 of 92. 17 of its 19 misses are collection funnels; 8 of
those sit at the edge of the export and are shown to the analyst as *insufficient evidence* — they are **not**
counted as found.

| Metric (holdout) | Definition | Rules | NEXORA |
|---|---|---:|---:|
| Alerts per dataset | review items at band *medium* or above | 42.6 | 9.5 |
| Legitimate networks flagged | legitimate planted networks with ≥ 1 alert | 80.5 % (103/128) | 37.5 % (48/128) |
| Recall | suspicious planted networks flagged; abstentions excluded | 95.7 % (88/92) | 79.3 % (73/92) |

> [!WARNING]
> **Read these numbers as behaviour on our own scenarios, not as accuracy on bank data.**
> * All data is synthetic and generated by the same team that wrote the detectors.
> * An audit ([PR #3](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/pull/3), not merged) found that this
>   holdout had already been read during v2 development, that every boundary abstention in `bench-v1` was planted
>   fraud (a label leak), and that P@K counts duplicate alerts on one network. The table therefore omits
>   abstention-inclusive recall and P@K, and the figures above are likely optimistic.
> * PR #3 adds a separately written, sealed evaluation with a pre-registered protocol; its numbers come from a
>   different generator and must not be compared with this table.

Every percentage is computed from the confusion counts in
[`benchmarks/results/bench-v1.json`](benchmarks/results/bench-v1.json) (commit `58440cc`, config hash, dataset
hashes recorded). Reproduce the run and the chart:

```bash
uv run python scripts/run_benchmark.py
```

```bash
python3 scripts/render_readme_figures.py
```

Full tables, ablations, negative results and error examples: [docs/EVALUATION.md](docs/EVALUATION.md).

## Architecture

```mermaid
flowchart LR
  user(["Analyst"]) --> gw["Gateway · Nginx<br/>auth, fail-closed"]
  gw --> web["Web · React + TypeScript"]
  gw --> api["API · FastAPI"]
  api --> db[("PostgreSQL 16")]
  worker["Worker<br/>lease · heartbeat · retry"] --> db
  worker --> core["nexora.analytics<br/>pure, deterministic pipeline"]
```

A modular monolith with one durable, database-backed job queue. The API never runs analysis in a request; the
worker computes outside any transaction and publishes atomically after re-checking its lease.

| Layer | Technology |
|---|---|
| Web | React 18, TypeScript, Vite, Cytoscape.js; OpenAPI-generated client |
| API | FastAPI, Pydantic v2; typed DTOs and one error envelope |
| Analysis | Python 3.13, NetworkX, exact integer arithmetic |
| Jobs | PostgreSQL lease worker (`FOR UPDATE SKIP LOCKED`), at-least-once with idempotent publish |
| Storage | PostgreSQL 16, SQLAlchemy 2, Alembic; `NUMERIC(38,0)` money, FK-enforced evidence links |
| Delivery | Docker Compose, GitHub Actions, Railway as code |

**Engineering decisions that matter for a bank**

* **Money is integer minor units** end to end (`NUMERIC(38,0)`, decimal strings in JSON, `BigInt` in TypeScript) — never floats.
* **Account and transaction ids are opaque strings**, so ids longer than 2⁵³ survive the browser intact.
* **Day-precision records never get a clock time.** Two transfers on the same day have an unknown order, and the chronology check reports *ambiguous* rather than guessing.
* **Analysis ids are content-derived (UUIDv5).** Re-running an analysis on the same data changes nothing.
* **Evidence that does not recompute from its source rows is quarantined**, never shown.
* **The audit trail is append-only**, enforced by a PostgreSQL trigger, and written in the same transaction as the decision.
* **Synthetic ground truth never enters the runtime database** or the detectors' input.

More: [system diagrams](docs/architecture/system.md) · [architecture and invariants](docs/ARCHITECTURE.md) ·
[interfaces](docs/INTERFACES.md) · [decisions](docs/ADR/0001-decisions.md).

## Quick start

Requires Docker with Compose v2. Everything binds to `127.0.0.1`.

```bash
docker compose up --build -d --wait
```

Open http://127.0.0.1:8080 → **Лаборатория** → *Сгенерировать набор* → *Запустить анализ* → *Перейти к алертам*.

For development with hot reload (Python via `uv`, web via `npm`):

```bash
make setup
```

```bash
make check
```

`make help` lists every target; each runs exactly what CI runs. Local databases, environment variables and
troubleshooting: [docs/development/local-setup.md](docs/development/local-setup.md). Cloud deployment (one
public gateway, private API/worker/database, approval-gated deploys):
[docs/deployment/railway.md](docs/deployment/railway.md).

## Repository

```text
src/nexora/
  domain/        money, transfers, chronology, ids — stdlib only
  ingest/        CSV adapter, row validation, quarantine, dedup
  analytics/     graph snapshot, detectors, temporal flow, peers, risk — no web/DB framework
  evaluation/    synthetic generator (labels kept separate) and benchmark harness
  application/   use cases: ingest, analysis jobs and publish, cases, read models
  persistence/   SQLAlchemy models and sessions
  api/ worker/   HTTP layer and the lease-based job runner
apps/web/        analyst UI (React + TypeScript)
apps/pitch/      the jury presentation (static React site)
migrations/      Alembic schema history
benchmarks/      committed benchmark artifact
scripts/         benchmark runner, README figures, OpenAPI export, Railway tooling
docs/            architecture, evaluation, limitations, deployment, design, research
```

## Quality and testing

| Gate | Command |
|---|---|
| Python lint, types, tests (unit + PostgreSQL integration) | `uv run ruff check src tests migrations && uv run mypy && uv run pytest` |
| Web types, unit and end-to-end tests | `cd apps/web && npx tsc -b && npx vitest run && npx playwright test` |
| API contract stays in sync | `make openapi` regenerates `apps/web/openapi.json` and `src/lib/api-types.ts` |
| Production images | CI builds the images and smoke-tests the running stack |

Strategy and what each layer covers: [docs/development/testing.md](docs/development/testing.md).

## Security and scope

* **Synthetic data only.** Not connected to Bank CenterCredit or any bank; holds no customer data.
* **Nothing is automated against customers.** NEXORA blocks nothing and sends nothing; it orders a review queue.
* **Demo identity.** Every action is attributed to one configured demo analyst; there is no SSO or role model yet.
* The cloud deployment is behind a fail-closed gateway and keeps the API, worker and database on a private network,
  but it is a hackathon deployment, not a bank-grade system.

Controls, known gaps and private vulnerability reporting: [SECURITY.md](SECURITY.md).

## Limitations of the current MVP

* **Legitimate hubs still alert, at medium.** Merchant settlement and treasury sweeps are flagged; peer counter-evidence keeps them out of the high band, but they are not cleared.
* **Family remittances look like distributions.** Nothing in transfer data alone separates them; KYC or MCC data would.
* **Slow funnels are missed.** Onward transfers later than the 7-day temporal window fall below the alert band.
* **Alerts are not yet correlated** by shared subject account, so one hub can appear as both a funnel and a fan-out.
* **Batch analysis** of a snapshot, not real-time scoring.

Full list: [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## Roadmap

| Status | Item |
|---|---|
| Done | Ingest, four structural detectors, temporal flow, peer statistics, coverage, risk policy v2, investigation UI, cases and audit, `bench-v1` |
| Done | Production images, fail-closed gateway, Railway as code, protected cloud demo |
| In review | [PR #3](https://github.com/SaginbekDaniel/SYNAPTIC-LABS/pull/3): competing-hypothesis engine, evaluation leakage fixes, sealed evaluation |
| Next | Offline replay on a bank's de-identified history and closed cases — the first honest measurement on real data |
| Planned | Correlate alerts by shared account; bridge/coordinator detector; named users via an identity-aware proxy |

## The pitch

[![The jury presentation: problem, method, product and results slides](docs/assets/readme/pitch-preview.webp)](https://pitch-production-1554324d.up.railway.app)

A three-minute interactive deck for the jury (Russian), built as a static React site in
[`apps/pitch/`](apps/pitch/README.md). Every benchmark figure on it is read from the committed artifact and pinned
by tests.

## Contributing, license, acknowledgements

Issues and pull requests are welcome — read [CONTRIBUTING.md](CONTRIBUTING.md) first.

No license has been chosen yet, so default copyright applies: the code is published for review, not licensed for
reuse.

Built by SYNAPTIC LABS for the ITU Hackathon 2026 Bank CenterCredit case, on FastAPI, SQLAlchemy, Alembic,
NetworkX, React, Vite and Cytoscape.js; licences reviewed in
[docs/research/LICENSE_MATRIX.md](docs/research/LICENSE_MATRIX.md).
