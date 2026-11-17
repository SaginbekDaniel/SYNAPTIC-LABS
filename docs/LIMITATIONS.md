# Known limitations (honest scope)

## What NEXORA is not

* Not connected to Bank CenterCredit or any bank. All data is **synthetic**.
* Not a real-time authorisation/blocking system. It is batch snapshot analysis triggered by jobs.
* Not proof of fraud or money laundering: outputs are review candidates for a human analyst.
* Authentication is **demo mode**: every request acts as `NEXORA_DEMO_ANALYST`. No SSO, no RBAC.

## Analytical limitations observed in this slice

* **Merchant-settlement hubs look like collection funnels.** In `demo-v1` seed 2026 the
  legitimate settlement processor (N2) is ranked *above* the planted collection funnel
  (priority 64 vs 55): it has more feeders and chronology-compatible onward payments. The
  current policy has no counter-signal (periodicity, very high fan-out) for legitimate hubs.
  This is an observed false positive, not yet measured as a rate.
* **Coincidental background chains.** Random background activity occasionally forms a
  3-hop pass-through path with compatible dates (one such `high` alert in `demo-v1` seed 2026).
* Only two signal families exist (STRUCTURE, TEMPORAL), so `critical` (requires 3) is unreachable
  by design and the maximum priority is 65.
* Temporal compatibility is an **upper bound** under unobserved intermediary balances; it
  never identifies the source of funds.
* Peer statistics, network context, fan-out/loop/bridge detectors are not implemented.

## Not yet built (spec stages)

* Stage 4 frozen benchmark: dev/validation/test splits, baselines, Precision@K, ablation —
  **no accuracy metrics exist yet**; none may be quoted.
* Durable replay runs (pause/resume cursor), late-event injection UI, evaluation screen.
* Case export, CSV upload UI (API endpoint exists), next-data-request task tracking.
