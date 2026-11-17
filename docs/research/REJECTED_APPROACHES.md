# Rejected approaches

| Approach | Seen in | Why rejected |
|---|---|---|
| Additive per-pattern scoring (sum of fixed points + centrality bonus) | Financial Forensics Engine `scoring.py` | Correlated patterns inflate scores (spec §10.3, §12); NEXORA credits ≤1 signal per family. |
| Automatic exclusion of "merchant-like" (amount CV) or "payroll-like" (batch timing) accounts | Financial Forensics Engine `smurf_detector.py` | Converts a heuristic into a silent clearance (spec §10.2). NEXORA caps priority and shows the counter-evidence instead. |
| Raising the fan-out amount threshold to remove family-remittance false positives | (our own option) | Threshold manipulation aimed at a known negative (spec Rule 5). The FP is reported (holdout N5 10/11). |
| Median/MAD z-scores for peer anomaly | Natural Intelligence's documented first version | Collapses on small discrete cohorts. |
| Tukey far-out fence k = 3 | Natural Intelligence | Measured: exceeds the bounded 0–100 % range for small cohorts and could never fire. Sensitivity at k = 1.0/2.0 reported. |
| Importing a rule engine (ezrules, Watch, Marble) | — | NEXORA's versioned, hashed policy already guarantees history is not rewritten; Marble is Elastic-2.0, Jube is AGPL-3.0. Offline shadow evaluation covers the need. |
| GNN models (Multi-GNN, DGFraud, LEX-GNN, …) | IBM, safe-graph | No independent labels, high leakage risk, weaker explainability, heavy dependencies. See `ARCHITECTURE_GAP_ANALYSIS.md`. |
| AMLSim as the data generator | IBM AMLSim | Java simulator + JanusGraph is disproportionate; NEXORA's generator is deterministic, label-separated and fast. |
| Day-bucket flow matching | UNRU `compatible_flow` | Loses transaction-level evidence; NEXORA's transfer-level max-flow already cites exact transactions. |
| Using the historical challenge parquet data | several BAITC repositories | Redistribution rights unverified; no licence. |
