# NEXORA AI — agent rules

Spec of record: `NEXORA_AI_MASTER_SPEC_CLAUDE_CODE.md` (team-supplied; P0 gates binding).

* Money = integer minor units (`int`/`NUMERIC(38,0)`), decimal strings in JSON, `BigInt` in TS. Never floats.
* Account/transaction ids are opaque strings end to end.
* Day-precision records never get a clock time; same day = ambiguous order.
* `nexora.domain` and `nexora.analytics` must not import FastAPI/SQLAlchemy.
* Analysis ids are content-derived (uuid5); keep publish idempotent.
* Synthetic ground truth never enters the runtime DB or detector input.
* No LLM in the evidence pipeline; no automatic action against customers.
* UI copy only via `apps/web/src/lib/i18n.ts`; styling only via tokens in `styles/tokens.css`.
* After API schema changes: `cd apps/web && npm run gen:api` and commit both generated files.
* Gates before commit: `uv run ruff check src tests migrations && uv run mypy && uv run pytest`,
  `cd apps/web && npx tsc -b && npx vitest run && npx playwright test`.
* Never quote accuracy metrics that were not produced by an executed benchmark run.
