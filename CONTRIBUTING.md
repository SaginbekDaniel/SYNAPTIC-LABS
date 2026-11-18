# Contributing to NEXORA AI

Thanks for helping. This file is the short version; setup details are in
[docs/development/local-setup.md](docs/development/local-setup.md) and the test strategy in
[docs/development/testing.md](docs/development/testing.md).

## Ground rules (binding — see `CLAUDE.md`)

* **Money is integer minor units** end to end (`int`/`NUMERIC(38,0)` in Python and SQL, decimal
  strings in JSON, `BigInt` in TypeScript). Never floats.
* **Account and transaction ids are opaque strings.** Never parse them as numbers.
* **Day-precision records never get a clock time.** Same day means ambiguous order.
* `nexora.domain` and `nexora.analytics` must not import FastAPI or SQLAlchemy.
* Analysis ids are content-derived (uuid5); publishing must stay idempotent.
* **Synthetic ground truth never enters the runtime database or detector input.**
* No LLM in the evidence pipeline and no automatic action against customers.
* UI copy only through `apps/web/src/lib/i18n.ts`; styling only through tokens in
  `apps/web/src/styles/tokens.css`.
* Never quote accuracy numbers that were not produced by an executed, committed benchmark run.

## Workflow

1. Branch from the default branch.
2. Make the change with tests. A bug fix starts with a test that fails without it.
3. After API schema changes: `make openapi` and commit both generated files.
4. Run every gate: `make check` (needs PostgreSQL; see local setup).
5. Open a pull request using the template. CI must be green, including the production-image
   smoke test.

## Commit messages

Imperative subject (≤ 72 characters) describing the behaviour change, then a body that explains
why. Reference issues as `owner/repo#123`.

## Deployment changes

Changes to `.railway/`, `Dockerfile`, `apps/web/Dockerfile` or `apps/web/docker/` must keep
`make iac-check` green and must not weaken the gateway (see `SECURITY.md`). Deployments are manual
and approval-gated (`.github/workflows/deploy-railway.yml`).
