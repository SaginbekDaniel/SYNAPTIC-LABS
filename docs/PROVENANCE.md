# Provenance

| Component | Origin | Basis |
|---|---|---|
| All code in `src/`, `apps/web/`, `tests/`, `migrations/`, `scripts/` | Written for NEXORA in this repository | Original work |
| Synthetic data | Generated at runtime by `src/nexora/evaluation/generator.py` (deterministic seeds) | Original; contains no real customer data |
| Third-party libraries | FastAPI, SQLAlchemy, Alembic, psycopg, Pydantic, NetworkX, React, React Router, Cytoscape.js, Vite, Playwright, Vitest | Installed from PyPI/npm under their own licences; versions pinned in `uv.lock` and `apps/web/package-lock.json` |

## External research (no code copied)

Twenty repositories were cloned at exact commits and read (never executed); licences and decisions are in
`docs/research/LICENSE_MATRIX.md` and `docs/research/ADOPTION_DECISIONS.md`. Ideas adopted, all independently
re-implemented: fan-out and loop formation kinds (Vantage AI, AMLSim, Natural Intelligence, UNRU AI),
cohort-relative Tukey fence (Natural Intelligence), decoy legitimate cycles and separated metric units
(SantanderAI gen-fraud-graph, Apache-2.0), capacity-based top-K evaluation (Fraud Detection Handbook — GPL-3.0,
ideas only; SignalGraph AML, MIT), perturbation-based stability checks (UNRU AI), offline shadow evaluation
(sofeikov/ezrules, Apache-2.0), rule-shaped baseline (Blnk Watch, Apache-2.0).

## Conceptual inspiration recorded in the first session (no code copied)

Per the master specification §2, the following *ideas* were described there as appearing
in reference projects. They were re-derived from the spec text, not from source code:

* Formation vocabulary (funnel, chain) and boundary/completeness reasoning — attributed to Vantage AI.
* Exact integer IDs and minor-unit money across a JS boundary — attributed to Jigas.
* Capacity-aware compatible flow — attributed to UNRU AI.
* Planted-scenario evaluation complemented by hard negatives — attributed to Natural Intelligence.
* Persisted case / audit entities with human approval — attributed to Synex.

The six BAITC-Hacks repositories contain **no licence file** at the audited commits, so their code may not be
reused; only ideas were taken.
