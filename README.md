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
* Two independent detector families: **structural** (collection funnel, layering chain) and
  **temporal** (capacity-constrained max-flow; same-day records are *ambiguous*, reversed dates *contradicted*).
* Coverage-aware abstention (`insufficient_evidence` at collection boundaries) and next-data requests.
* Versioned risk policy with correlation guard and evidence caps.
* Investigation UI: alert queue → hypothesis → reasons → highlighted source transfers → formation graph
  → case decision with optimistic concurrency and append-only audit.

See `docs/LIMITATIONS.md` for what does **not** work yet (notably: no benchmark metrics exist).

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
| `docs/` | Architecture, interfaces, audit/provenance, limitations, plan, test report |
