# Source code map — idea → external source → NEXORA implementation

No external code was copied. "Source" names where the idea was observed; the NEXORA file is an independent
implementation with its own tests.

| Capability | Observed in (file @ commit) | NEXORA implementation | Tests |
|---|---|---|---|
| Fan-out formation | Vantage `formations.py::_fan_outs` @577955; AMLSim `alertPatterns.csv` fan_out | `src/nexora/analytics/structural/fan_out.py` | `tests/unit/test_v2_detectors.py` (fan-out tests) |
| Time-respecting loops | Natural Intelligence `motifs.py::time_respecting_cycles`; UNRU `patterns.py::short_cycles`; AMLSim cycle | `structural/cycle.py` + layered max-flow in `temporal/flow.py` | cycle tests incl. contradicted chronology, budget |
| Peer-relative anomaly with Tukey fence | Natural Intelligence `anomaly.py` | `analytics/statistical/peer.py` | peer tests, recomputable evidence |
| Two-way relationship ≠ consolidation | (no external source; derived from our dev-split loan false positives) | `funnel.py`, `fan_out.py` `exclude_returning_*` | returning-feeder / recipient tests |
| Decoy legitimate cycles | gen-fraud-graph `typologies.py::_generate_decoys` | `evaluation/generator.py::_treasury_sweep` (N7) | benchmark family table |
| Separate account / ring metric units | gen-fraud-graph `evaluate.py::evaluate` | `evaluation/benchmark.py::summarize` (scenario / alert / queue) | `tests/unit/test_benchmark.py` |
| Capacity-limited top-K evaluation | Handbook ch. 4 (CP@k); SignalGraph README | `benchmark.py` queue metrics P@K, Recall@K | idem |
| Parameter perturbation / dropout | UNRU `stability.py` | `benchmark.py` `PERTURBATIONS`, `SENSITIVITY` | determinism tests |
| Rule-shaped baseline | Watch `examples/*.ws`; Forensics `smurf_detector.py` | `benchmark.py::rules_method` (B1) | harness tests |
| Shadow evaluation of policy versions | ezrules `shadow_evaluation_queue.py` | `benchmark.py::VARIANTS`, `config_variant` | v1-variant test |
