# NEXORA AI — Explainable Financial Fraud-Network Investigation

**SYNAPTIC LABS · ITU Hackathon 2026 (Bank CenterCredit case) · prototype**

NEXORA turns transaction records into **evidence-backed, time-consistent, coverage-aware
network investigations** and helps a human analyst prioritise, verify and decide — without
claiming that a graph anomaly proves a crime.

> Demo uses **synthetic data only**. No bank integration, no account blocking, no real
> customer data. Priority is a triage ranking, not a fraud probability.

## What works today

* Synthetic scenario lab (suspicious formations, legitimate lookalikes, hard negatives) and CSV import
  with row-level quarantine and idempotent re-import.
* Directed graph snapshots with exact integer money and string account ids (incl. ids > 2^53).
* Three signal families: **structural** (collection funnel, coordinated distribution / fan-out, layering
  chain, time-checked circular flow), **temporal** (capacity-constrained max-flow; same-day records are
  *ambiguous*, reversed dates *contradicted*) and **peer statistics** (turnover concentration vs. an
  activity-matched cohort, used as corroboration *or* counter-evidence).
* Coverage-aware abstention (`insufficient_evidence` at collection boundaries) and next-data requests.
* **Competing hypotheses** (`hypotheses-v1`) for funnel and fan-out formations: the suspicious reading and the
  legitimate explanations with the same shape (recurring business, scheduled payout, lending, one-off collections,
  remittances), each tested against dependency-grouped observations; untestable alternatives are listed with the
  data that would decide. Shown in the investigation as *Альтернативные объяснения*.
* Versioned risk policy (`risk-policy-v3`) with correlation guard and named evidence gates; a formation whose
  legitimate explanation is favoured by two independent observation groups is stored at `low`, never deleted.
* **Reproducible synthetic benchmark** (`scripts/run_benchmark.py`): dev / validation / holdout seeds,
  baselines, ablations, robustness — rendered on the **Evaluation** screen and in `docs/EVALUATION.md`.
* Investigation UI: alert queue → hypothesis → reasons → highlighted source transfers → formation graph
  → case decision with optimistic concurrency and append-only audit.

### Measured on the sealed split `sealed-v1` (60 datasets, independent generator, evaluated once)

Protocol and decision rule were locked and pushed before the hypothesis engine was written
(`docs/evaluation/EXPERIMENT_PROTOCOL.md`). Baseline = the configuration merged at `4c01a7a`.

| | NEXORA v2 (baseline) | NEXORA v3 | Difference (95 % paired bootstrap) |
|---|---:|---:|---|
| Legitimate networks flagged (scenario FPR) | 50.7 % | **15.9 %** | −34.8 pp [−40.2, −29.1] |
| Suspicious networks flagged (scenario recall) | 73.3 % | **74.8 %** | +1.5 pp [0.0, +3.2] |
| Legitimate networks reaching *high* priority | 17.8 % | **9.8 %** | −8.0 pp [−12.3, −4.3] |
| Distinct planted networks in the first 5 alerts (distinct P@5) | 46.5 % | **59.3 %** | +12.8 pp [+8.6, +17.6] |

Still indistinguishable without KYC or merchant data: event ticketing (22/23 flagged), charity campaigns (13/36),
family remittances (5/20). Slow accumulation (recurring-mule collection) is missed by both versions (1/8).
Details, ablations and negative results: `docs/evaluation/RESULTS.md`; audit: `docs/architecture/DEEP_AUDIT.md`.

### Historical: v2 on the `bench-v1` holdout (now exposed — see `docs/architecture/LEAKAGE_ANALYSIS.md`)

| | NEXORA v1 (before) | NEXORA v2 | Best simple baseline |
|---|---:|---:|---|
| Suspicious networks flagged (scenario recall) | 60.9 % | **79.4 %** | rules: 95.7 % at 42.6 alerts/dataset |
| Legitimate networks reaching *high* priority | 43.8 % | **6.3 %** | — (baselines have no priority bands) |
| Share of top-5 alerts that are planted fraud (P@5) | 31.3 % | **48.3 %** | turnover ranking: 34.0 % |
| Planted networks found in the first 5 alerts (Recall@5) | 45.8 % | **73.6 %** | rules: 43.6 % |

Synthetic data written by the same team that wrote the detectors: these numbers show behaviour on our scenarios,
not accuracy on real bank data. Full tables, negative results and error examples: `docs/EVALUATION.md`.
See `docs/LIMITATIONS.md` for what does **not** work.

## Run with Docker

```bash
cp .env.example .env
```

```bash
docker compose up --build -d
```

Open http://127.0.0.1:8080 → **Fraud Lab** → *Сгенерировать набор* → *Запустить анализ* → *Перейти к алертам*.
Migrations run automatically (`migrate` service). API docs: http://127.0.0.1:8000/docs.

## Local development

Requires Python 3.12+ with [uv](https://docs.astral.sh/uv/), Node 22, PostgreSQL 16 with a `nexora` role/database.

```bash
uv sync
```

```bash
uv run alembic upgrade head
```

```bash
uv run uvicorn nexora.api.main:app --port 8000
```

```bash
uv run python -m nexora.worker.runner
```

```bash
cd apps/web && npm ci && npm run dev
```

The dev UI is served at http://127.0.0.1:5173 and proxies `/api` to port 8000.

## Benchmark

```bash
uv run python scripts/run_benchmark.py
```

Writes `benchmarks/results/bench-v1.json` (served by `GET /api/v1/evaluation`) and `docs/EVALUATION.md`.
This is the historical v2 benchmark, pinned to the exact v2 configuration (it reproduces the committed artifact).
The locked comparison of the current configuration against that baseline is:

```bash
uv run python scripts/run_sealed_evaluation.py --split sealed --out /tmp/sealed.json
```
About one minute on one CPU core; deterministic except wall-clock latency.

## Tests

```bash
uv run pytest
```

```bash
cd apps/web && npx vitest run && npx playwright test
```

Integration tests use `NEXORA_TEST_DATABASE_URL` (default `…/nexora_test`); Playwright starts its own
API + worker against `NEXORA_E2E_DATABASE_URL` (default `…/nexora_e2e`) and resets that database.

## Repository map

| Path | Contents |
|---|---|
| `src/nexora/domain` | Money, transfers, chronology, typed analysis contracts |
| `src/nexora/analytics` | Graph snapshot, detectors, temporal flow, coverage, risk, pipeline |
| `src/nexora/application` | Ingest, analysis jobs/publishing, cases, read models |
| `src/nexora/api` · `worker` | FastAPI app · lease-based job worker |
| `configs/` | Versioned detector and risk-policy configuration (hashed into every snapshot) |
| `apps/web` | React + TypeScript + Cytoscape UI |
| `src/nexora/evaluation` | Synthetic generator and benchmark harness (labels never reach detectors) |
| `benchmarks/results` | Committed benchmark artifact of an executed run |
| `docs/` | Architecture, interfaces, evaluation, limitations, plan, test report |
| `docs/research` | GitHub landscape, deep audit, scorecard, licence matrix, adoption and rejection decisions |
