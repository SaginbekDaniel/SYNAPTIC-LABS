# syntax=docker/dockerfile:1
# One Python image for the api, worker and migrate roles (one validated lockfile).
# The role is chosen by the start command:
#   api      default CMD (uvicorn)
#   worker   python -m nexora.worker.runner
#   migrate  alembic upgrade head
ARG PYTHON_IMAGE=python:3.13-slim

# ---- build: resolve the locked environment with uv -------------------------------------------
FROM ${PYTHON_IMAGE} AS build
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
RUN pip install --no-cache-dir uv==0.11.32
WORKDIR /app
# Dependencies first: this layer is reused until pyproject.toml or uv.lock change.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev

# ---- runtime: interpreter + virtualenv + application files, no build tooling ----------------
FROM ${PYTHON_IMAGE} AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH="/app/.venv/bin:$PATH"
RUN useradd --system --uid 10001 --no-create-home --shell /usr/sbin/nologin nexora
WORKDIR /app
COPY --from=build /app/.venv ./.venv
COPY --from=build /app/src ./src
# Paths are resolved relative to src/nexora (configs/, benchmarks/), so the repository layout is kept.
COPY configs ./configs
COPY migrations ./migrations
COPY alembic.ini ./
COPY benchmarks/results ./benchmarks/results
# Files stay root-owned and read-only for the runtime user; the application writes nothing to disk.
USER 10001
EXPOSE 8000
# exec hands PID 1 to uvicorn so SIGTERM triggers its graceful shutdown.
# NEXORA_BIND_HOST="::" listens on IPv6 + IPv4 (Railway private networking); PORT follows the platform.
CMD ["sh", "-c", "exec uvicorn nexora.api.main:app --host \"${NEXORA_BIND_HOST:-0.0.0.0}\" --port \"${PORT:-8000}\" --timeout-graceful-shutdown 20 --no-server-header"]
