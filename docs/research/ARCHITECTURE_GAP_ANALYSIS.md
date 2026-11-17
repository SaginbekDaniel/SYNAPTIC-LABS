# Architecture gap analysis (before → after this iteration)

| Spec area | State found at `66b6c69` | Gap | Action taken | Evidence |
|---|---|---|---|---|
| §8.2 formation detectors | funnel, chain | no fan-out, no circular flow, no bridge | added fan-out and time-checked cycle; bridge **not** added | holdout: terminal distributions 0/8 → 8/8, loops 9/13 → 13/13 |
| §10 peer / behavioural analysis | not implemented | merchant hub ranked above planted funnel (documented) | `PEER_STATISTICS` family + policy cap | demo-v1 seed 2026: hub moves from #1 *high* to *medium* |
| §10.2 legitimate look-alikes | payroll, merchant, reimbursement, reverse chain | no supplier, remittance, loan, treasury decoys | 4 new hard negatives | family table in `docs/EVALUATION.md` |
| §12 risk engine | risk-policy-v1, 2 families | `critical` unreachable; no counter-evidence | risk-policy-v2, named cap gates | `test_peer_counter_evidence_caps_band_with_named_gate` |
| §13 rule lifecycle | versioned/hashed config, immutable history | no shadow comparison | offline shadow/ablation harness | `benchmarks/results/bench-v1.json` |
| §14–15 benchmark | **none** ("no accuracy metrics exist") | everything | `bench-v1` suite, dev/validation/holdout, baselines B0–B4, ablations, robustness | `docs/EVALUATION.md` |
| §19 Screen F | missing | — | Evaluation screen from the persisted artifact | `e2e/evaluation.spec.ts` |
| §16 GNN | none | — | **rejected for MVP** (below) | — |

## GNN research track (spec §16)

1. *Labelled data?* Only our own synthetic labels (a few hundred scenarios). Training on them would learn the
   generator, not fraud.
2. *Leakage?* High: scenario families share generators; a model would memorise topology templates.
3. *Explainable?* Not to the evidence standard NEXORA enforces (every reason recomputable from transactions).
4. *Inference cost?* Requires PyTorch Geometric — a large new dependency stack for the worker image.
5. *Beats deterministic baselines?* Unknown and not measurable honestly without independent labelled data.
6. *Maintainable in the hackathon?* No.

**Decision:** no GNN in the MVP. Revisit only with an independent labelled dataset (e.g. IBM AML on Kaggle,
licence permitting) and as a ranking feature behind the existing evidence gates.

## Remaining gaps

Bridge/coordinator detector (§8.2), NETWORK_CONTEXT family, durable replay runs and late-event snapshots,
alert correlation across formations that share a hub (a merchant hub can raise both a funnel and a fan-out
alert), case export.
