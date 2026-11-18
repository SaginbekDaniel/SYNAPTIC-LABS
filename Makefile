# Thin aliases for the commands documented in docs/development/local-setup.md.
# Every target runs the same command CI runs; nothing here hides extra logic.
.DEFAULT_GOAL := help
WEB := apps/web

.PHONY: help setup migrate api worker web lint format typecheck test e2e check build openapi up down smoke iac-check

help: ## List targets
	@grep -hE '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-11s %s\n", $$1, $$2}'

setup: ## Install Python (uv) and web (npm) dependencies
	uv sync --frozen
	cd $(WEB) && npm ci

migrate: ## Apply database migrations (NEXORA_DATABASE_URL)
	uv run alembic upgrade head

api: ## Run the API on :8000 with reload
	uv run uvicorn nexora.api.main:app --reload --port 8000

worker: ## Run the analysis worker
	uv run python -m nexora.worker.runner

web: ## Run the web dev server on :5173 (proxies /api to :8000)
	cd $(WEB) && npm run dev

lint: ## Ruff lint + format check
	uv run ruff check src tests migrations
	uv run ruff format --check src tests migrations

format: ## Apply Ruff formatting
	uv run ruff format src tests migrations

typecheck: ## mypy + TypeScript
	uv run mypy
	cd $(WEB) && npx tsc -b

test: ## pytest (integration tests need PostgreSQL) + vitest
	uv run pytest
	cd $(WEB) && npx vitest run

e2e: ## Playwright E2E (starts its own API + worker; resets NEXORA_E2E_DATABASE_URL)
	cd $(WEB) && npx playwright test

check: lint typecheck test e2e iac-check ## Every gate required before a commit

build: ## Production web build
	cd $(WEB) && npx vite build

openapi: ## Regenerate apps/web/openapi.json and src/lib/api-types.ts (commit both)
	cd $(WEB) && npm run gen:api

iac-check: ## Validate .railway/railway.ts and its security invariants
	cd .railway && npm ci --no-audit --no-fund && npm run check

up: ## Production-like local stack on http://127.0.0.1:8080 (docker compose)
	docker compose up --build -d --wait

down: ## Stop the local stack (data volume is kept; add -v to docker compose down to drop it)
	docker compose down

smoke: ## Smoke test a running gateway (NEXORA_SMOKE_URL, _USER, _PASSWORD)
	cd $(WEB) && npx playwright test -c playwright.smoke.config.ts
