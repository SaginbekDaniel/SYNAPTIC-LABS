# Provenance

| Component | Origin | Basis |
|---|---|---|
| All code in `src/`, `apps/web/`, `tests/`, `migrations/`, `scripts/` | Written for NEXORA in this repository | Original work |
| Synthetic data | Generated at runtime by `src/nexora/evaluation/generator.py` (deterministic seeds) | Original; contains no real customer data |
| Third-party libraries | FastAPI, SQLAlchemy, Alembic, psycopg, Pydantic, NetworkX, React, React Router, Cytoscape.js, Vite, Playwright, Vitest | Installed from PyPI/npm under their own licences; versions pinned in `uv.lock` and `apps/web/package-lock.json` |

## Conceptual inspiration (no code copied)

Per the master specification §2, the following *ideas* were described there as appearing
in reference projects. They were re-derived from the spec text, not from source code:

* Formation vocabulary (funnel, chain) and boundary/completeness reasoning — attributed to Vantage AI.
* Exact integer IDs and minor-unit money across a JS boundary — attributed to Jigas.
* Capacity-aware compatible flow — attributed to UNRU AI.
* Planted-scenario evaluation complemented by hard negatives — attributed to Natural Intelligence.
* Persisted case / audit entities with human approval — attributed to Synex.

Repository licences for these projects were **not verified** (see `REFERENCE_AUDIT.md`).
