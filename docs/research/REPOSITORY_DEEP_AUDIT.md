# Repository deep audit

Classification of every finding: **Documented** (stated in README/docs), **Implemented** (seen in source at the
audited commit), **Verified** (executed by us). We did not execute third-party code, so no external finding is
*Verified*; what NEXORA re-implemented is verified by NEXORA's own tests and benchmark.

## Vantage AI (`src/moneygraph/formations.py`, `completeness.py`, `flows.py`, `priority.py`)
* **Implemented:** five formation kinds with thresholds in one `RULES` table — funnel (≥3 feeders, ≥50 % of
  feeder outflow), chain (forward share ≥50 %, interior degree ≤3), reciprocal loop (pairs, cycles ≤4), fan-out
  (≥8 *terminal* receivers), bridge (cut vertex of a community ≥12). Breaking point via immediate dominators /
  articulation points.
* **Implemented:** `completeness.py` turns crawl design into per-node fields: hop-4 nodes are *crawl stops*, not
  terminals; inbound funding of seeds is never observed.
* **Documented:** on their dataset funnels are rare (8 of 653 formations) and the highest in-degree node is a
  "busy account rather than a collection point".
* **Relevance to NEXORA:** confirms the funnel definition NEXORA already used and motivated adding fan-out and
  loop kinds; NEXORA's coverage engine already treats boundary nodes as unobserved, not terminal.
* **Weakness:** no licence; pandas-scale batch scripts; scoring is a weighted sum per formation.

## UNRU AI (`moneygraph/patterns.py`, `stability.py`, `evidence.py`)
* **Implemented:** `compatible_flow` — max-flow with daily buckets and +1/+2-day lags, capacities used once;
  right-censoring of inflows too close to the window end; bounded canonical 3–4 cycles.
* **Implemented:** `stability.py` — fixed parameter perturbations and 5 % edge dropout over three seeds,
  comparing rankings (priority = weighted sum of volume, neighbours, seed reach, role, PageRank).
* **Relevance:** independently matches NEXORA's existing temporal flow design; motivated the robustness and
  threshold-sensitivity sections of our benchmark.
* **Gap vs NEXORA:** day buckets, not transfers, so evidence cannot cite exact transactions.

## Natural Intelligence (`src/motifs.py`, `src/anomaly.py`)
* **Implemented:** time-respecting cycles (dates must increase around the loop); pass-through transaction
  matching; shared-receiver significance under a configuration model.
* **Implemented + documented reasoning:** depth-relative anomaly with a **Tukey far-out fence Q3+3·IQR**,
  explicitly because median/MAD z-scores collapsed on small discrete features (their first version flagged a
  third of the graph).
* **Relevance:** directly shaped NEXORA's peer-statistics design (cohort-relative Tukey fence). We measured that
  k = 3 cannot fire on a bounded 0–100 % statistic with small cohorts and use k = 1.5 (sensitivity tested at 1.0
  and 2.0 — no change in recall, see `docs/EVALUATION.md`).

## Jigas, Moggers, Synex
* **Jigas — Implemented:** `test_contract.py` contract tests, exact string account ids, deterministic report
  generation; threshold and community-stability evaluation scripts. NEXORA already had equivalent guarantees
  (DATA-001…003); nothing new adopted.
* **Moggers — Implemented:** React + TypeScript `GraphCanvas.tsx` with Playwright tests (2 spec files). NEXORA's
  Cytoscape canvas is comparable; not used.
* **Synex — Implemented:** `ai/governance.py` wraps an LLM provider behind a `GovernedProvider` with a
  deterministic fallback; persisted cases and audit. NEXORA keeps **no LLM in the evidence pipeline** (ADR-014);
  the governance pattern is noted for a future optional narrator.

## IBM AMLSim
* **Implemented:** parameter files define alert typologies (`fan_in`, `fan_out`, `cycle` in the 1K/10K sets; the
  README and Java sources add bipartite, stack, scatter-gather, gather-scatter) and *normal* models (single,
  fan-in, fan-out, forward, mutual, periodical).
* **Relevance:** reference vocabulary for NEXORA's suspicious and legitimate scenario families; especially the
  fact that **normal behaviour also contains fan-in/fan-out/forward/periodic shapes**.
* **Not adopted:** Java multi-agent simulator, JanusGraph — far heavier than needed for a reproducible
  hackathon benchmark.

## SantanderAI gen-fraud-graph (`typologies.py`, `evaluate.py`)
* **Implemented:** fraud rings plus **decoy legitimate high-value cycles** (treasury sweeps, payroll funding,
  merchant settlement) written as normal traffic to defeat topology-only and amount-only detectors.
* **Implemented:** separate account-level and ring-level precision/recall with a ring-coverage threshold.
* **Relevance:** NEXORA added the intercompany treasury-sweep decoy (N7) and keeps scenario-level and alert-level
  metrics separate.

## masenka31 fraud-benchmark, Fraud Detection Handbook, SignalGraph AML
* **fraud-benchmark — Documented + implemented:** synthetic label delay per campaign, censoring of training
  labels, time-based splits. NEXORA's detectors are unsupervised, so label delay does not bias them; we record
  the limitation instead of simulating it.
* **Handbook (GPL-3.0, ideas only):** threshold-free metrics are poorly suited to imbalance; argues for
  **Card Precision top-k** under investigator capacity.
* **SignalGraph — Documented:** frames detection as "if the team can investigate N alerts, which first?".
* **Relevance:** NEXORA's primary queue metrics are P@K and Recall@K per analyst queue.

## ezrules, Blnk Watch, Marble
* **ezrules — Implemented:** rule statuses draft/active/archived with history, rollouts, shadow evaluation queue
  and backtests (≈790 test functions in the repo).
* **Watch — Implemented:** a rule DSL (30 example rules, e.g. "≥5 transactions from the same source within
  PT30M"); used as the shape of NEXORA's B1 rules baseline.
* **Marble:** Elastic-2.0; full decision engine with case manager. Not inspected beyond licence and layout.
* **Decision:** NEXORA's policy is already versioned and hashed into every snapshot; old assessments are never
  rewritten. We implemented **offline shadow evaluation** (any policy/detector variant replayed against the
  benchmark) rather than importing a rule engine.

## Financial Forensics Engine (MIT)
* **Implemented:** cycle, smurf (fan-in/out in 72 h), shell-chain, rapid-movement and structuring detectors;
  account score = **sum of fixed per-pattern points** plus centrality bonus; merchant exclusion by coefficient of
  variation of incoming amounts; payroll exclusion if all outgoing transfers fall within a batch window.
* **Not tested:** the repository contains `test_integration.py` with no test functions.
* **Assessment:** additive scoring double-counts correlated patterns and auto-excludes look-alikes — both
  explicitly forbidden by the NEXORA spec (§10.2, §12). See `REJECTED_APPROACHES.md`.

## IBM Multi-GNN
* **Implemented:** GIN/GAT/PNA/RGCN with directed-multigraph adaptations (ego IDs, port numbering, reverse
  message passing) for edge classification on the IBM AML Kaggle data. Requires PyTorch Geometric and labelled
  data. Evaluated in the GNN track of `ARCHITECTURE_GAP_ANALYSIS.md`.
