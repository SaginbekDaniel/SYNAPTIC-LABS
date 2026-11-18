# Testing

Run every gate with `make check` (each target maps to one command; see the `Makefile`).
CI (`.github/workflows/ci.yml`) runs the same commands plus the production-image job.

| Layer | Command | What it covers |
|---|---|---|
| Lint / format | `make lint` | Ruff rules and formatting (`src`, `tests`, `migrations`) |
| Types | `make typecheck` | mypy (`nexora`), `tsc -b` (web) |
| Python unit | `uv run pytest tests/unit` | money, validation, detectors, temporal flow, risk, benchmark harness, deployment settings |
| Python integration | `uv run pytest tests/integration` | PostgreSQL persistence, API end to end, gateway token, commit-before-response; uses `NEXORA_TEST_DATABASE_URL` and **resets** that database |
| Migrations | `uv run alembic upgrade head && uv run alembic check` | migrations apply and match the ORM |
| OpenAPI contract | `make openapi` then `git diff --exit-code` | generated client matches the API |
| Web unit | `npx vitest run` | formatting, i18n completeness, UI logic |
| Browser E2E | `make e2e` | starts its own API + worker on `NEXORA_E2E_DATABASE_URL` (reset), desktop 1440 px and mobile 390 px |
| Deployment definition | `make iac-check` | `.railway/railway.ts` type-checks; security invariants hold |
| Deployed smoke | `make smoke` | any running gateway (local compose or Railway); adds synthetic data only, never resets |

The smoke test reads `NEXORA_SMOKE_URL`, `NEXORA_SMOKE_USER`, `NEXORA_SMOKE_PASSWORD`
(omit the last two when gateway auth is off). Set `NEXORA_SMOKE_SCREENSHOTS=<dir>` to save screenshots.

Rules: a bug fix starts with a test that fails on the old code; never weaken a test to make it
pass; databases used by tests must be disposable.
