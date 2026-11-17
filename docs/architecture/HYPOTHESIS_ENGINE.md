# Hypothesis engine (`hypotheses-v1`)

Transactions → graph → **candidate detection** → **hypotheses** → **falsification tests** →
**competing explanations** → uncertainty → investigation priority.

Detectors remain candidate generators: a funnel or fan-out says where to look, not what happened.
For each hub formation the engine states the suspicious hypothesis and the legitimate explanations
that produce the same shape, tests what each predicts, and reports a verdict. No LLM is involved;
everything is deterministic, versioned and recomputable.

Code: `src/nexora/analytics/hypotheses/engine.py` (pure; no FastAPI/SQLAlchemy). Contracts:
`HypothesisTest`, `HypothesisEvaluation`, `HypothesisAssessment` in `src/nexora/domain/analysis.py`.
Persistence: table `hypothesis_assessments` (migration 0003, insert-only, downgrade refuses while rows
exist). API: additive, nullable `hypotheses` on `GET /api/v1/alerts/{id}`. UI: "Альтернативные
объяснения" in the investigation summary.

## Scope (vertical slice)

Funnel and fan-out formations only — they produced the largest false-positive families. Chains and
cycles have `hypotheses: null`; extending to them is future work and needs its own evaluation.

## Registry

| Id | Polarity | Kinds | Testable on transactions | Data that would decide |
|---|---|---|---|---|
| `collection_through_intermediary` | suspicious | funnel | yes | ownership/KYC, counterparty relationships |
| `coordinated_distribution` | suspicious | fan-out | yes | ownership/KYC, recipients' onward history |
| `recurring_business_activity` | legitimate | both | yes | merchant category, business registration |
| `scheduled_payout` | legitimate | fan-out | yes | payer registration |
| `loan_disbursement_and_repayment` | legitimate | both | yes (one group) | loan agreements |
| `one_off_legitimate_collection` | legitimate | funnel | **no** | merchant category, payment references |
| `personal_remittance` | legitimate | fan-out | **no** | KYC relationships, income source |

Untestable alternatives are always reported. A "suspicious explanation favoured" verdict is relative
to the *testable* alternatives and the UI says so.

## Observations and groups

New observations are emitted as `aggregate_fact` evidence (validated, FK-linked to transactions):
`HYP_COUNTERPARTY_RECURRENCE` (share of counterparties transacting on ≥ 2 distinct days),
`HYP_ACTIVITY_SPAN` (subject's first–last activity / snapshot window), `HYP_PAYOUT_SCHEDULE` (share
of a distribution paid on its largest day). Temporal-flow and peer evidence are cited, not recomputed.

| Group | Reads | Why separate |
|---|---|---|
| `flow_timing` | temporal max-flow status | ordering and capacity of specific funds |
| `subject_activity` | peer concentration **and** activity span | both derive from the subject's activity dates → one vote |
| `counterparty_relationship` | recurrence | relationship history with each counterparty |
| `payout_schedule` | largest-day share | batch payment structure |
| `two_way` | returning counterparties | reverse-direction flows |

## Scoring and verdict

Per hypothesis: each group votes +1 (all its tests consistent), −1 (all inconsistent) or 0 (mixed or
unavailable). Status: `supported` (≥ 2 consistent groups, none inconsistent), `refuted`
(inconsistent − consistent ≥ 2), `weakened` (any inconsistent), `not_established`, `untestable`.

Verdict: `insufficient_data` if fewer than two groups could be evaluated for the suspicious
hypothesis; `benign_explanation_favoured` if a legitimate hypothesis is supported and the suspicious
one has a negative balance; `suspicious_explanation_favoured` if the suspicious one is supported and
every testable alternative has a negative balance; otherwise `inconclusive`.

Thresholds (fixed a priori, `configs/detectors.yaml`): recurring ≥ 2 distinct days; recurrence ≥ 0.5
consistent with business / ≤ 0.2 with one-off; span ≥ 0.8 established / ≤ 0.3 short; one payment run
≥ 90 % on one day.

## Decision integration (`risk-policy-v3`)

Only one gate: `benign_explanation_favoured → low`. The formation, its evidence, signals and
hypotheses stay stored; the reason `BAND_CAPPED_BY_EVIDENCE` names the gate. The v2 score, bands
and other gates are unchanged, so v2 remains a reproducible baseline (`VARIANTS["v2_shipped"]`).

Evaluated and **not adopted** on dev: `inconclusive → medium` (no effect). Dev ablation without peer
statistics looked better and was not adopted; on sealed it raised high-band FPR (0.098 → 0.127).

## Measured effect

Sealed split (see `../evaluation/RESULTS.md`): scenario FPR 0.507 → 0.159 at recall 0.733 → 0.748,
high-band FPR 0.177 → 0.098. The ablation "engine without gate" equals the baseline: the effect comes
from the gate; the engine itself adds explanations. Median pipeline latency per sealed dataset was
83.2 ms (candidate) vs 73.5 ms (baseline) and 79.8 ms (engine removed) — single-core wall clock, noisy.

## Known limits

* Recurrence and span are evadable one at a time; the two-group requirement is the defence, and the
  sealed recurring-mule family shows the residual risk is on the detection side (F-06), not in a benign
  verdict.
* Legitimate one-off collections (ticketing, charity) and personal remittances are indistinguishable
  from fraud on transaction data: sealed 22/23, 13/36 and 5/20 still alert. The engine reports them
  as untestable instead of guessing.
* Peer cohorts and activity span are relative to one snapshot; history before the window is unknown
  (stated as a limitation on the evidence).
