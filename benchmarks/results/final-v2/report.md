# Benchmark report — final-v2

> SYNTHETIC BENCHMARK. All networks, labels and metrics come from the NEXORA synthetic scenario generator, not from bank data. Results describe behaviour on this synthetic distribution only and are not estimates of real-world fraud detection accuracy.

* Benchmark: `nexora-bench-v1`, master seed `2026`
* Code: `167d4fb4a4325ae70722446f4100b9a35b271c92`
* Created: 2026-11-17T06:36:11+00:00 · duration 75.5 s
* Host: Intel(R) Xeon(R) Processor @ 2.10GHz · Python 3.13.18 · networkx 3.7
* Splits evaluated: dev, val, test

## Evaluation units

* **unit_scenario** — One planted scenario per network. TP = a raised alert matches a planted suspicious scenario; FP = a raised alert matches a planted benign scenario.
* **unit_alert** — Every raised alert. True only if it matches a planted suspicious scenario; alerts on benign scenarios or unlabelled background are false.
* **unit_queue** — Raised alerts of a split pooled and sorted by review score. Precision@K/Recall@K count distinct suspicious scenarios; duplicate alerts on one scenario waste a slot.
* **unit_account** — Accounts in raised alerts vs accounts of planted suspicious scenarios. Over-counts large networks; reported separately and never combined with scenario metrics.

Matching rule: A prediction matches a scenario when >= 50% of its accounts belong to the scenario and, if it cites transactions, at least one is a planted scenario transaction.

## Methods

| Method | Group | Description | Fitted / config |
|---|---|---|---|
| B0_volume | baseline | Accounts ranked by total observed in+out volume | threshold=117335932.000 {} |
| B1_centrality | baseline | Amount-weighted PageRank (relative to uniform) | threshold=0.495 {} |
| B2_static_rules | baseline | Large single transfer, 7-day fan-in or fan-out rules | threshold=1.000 {'large_minor': 50000000, 'fan': 10} |
| B3_v1_structural_only | nexora | v1 formations, structure credited only | 843882cd4c24 |
| B4_v1_structural_temporal | nexora | v1 engine as shipped: structure + temporal + coverage | 3e251bd89c48 |
| B5_v2_full | nexora | v2 engine: all detectors, context, coverage | 5c556030d218 |

## Split `dev`

### Scenario unit (primary)

| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 59 | 113 | 1 | 31 | 0.343 [0.32, 0.36] | 0.983 [0.95, 1.00] | 0.509 | 0.785 | 0.017 |
| B1_centrality | 59 | 129 | 1 | 15 | 0.314 [0.30, 0.33] | 0.983 [0.95, 1.00] | 0.476 | 0.896 | 0.017 |
| B2_static_rules | 55 | 114 | 5 | 30 | 0.325 [0.30, 0.35] | 0.917 [0.83, 0.98] | 0.480 | 0.792 | 0.083 |
| B3_v1_structural_only | 49 | 95 | 11 | 49 | 0.340 [0.30, 0.38] | 0.817 [0.72, 0.92] | 0.480 | 0.660 | 0.183 |
| B4_v1_structural_temporal | 39 | 48 | 21 | 96 | 0.448 [0.37, 0.52] | 0.650 [0.53, 0.77] | 0.531 | 0.333 | 0.350 |
| B5_v2_full | 54 | 45 | 6 | 99 | 0.545 [0.48, 0.61] | 0.900 [0.82, 0.97] | 0.679 | 0.312 | 0.100 |

### Alert queue, alert and account units

| Method | Alerts | Alert precision | Alerts/network | Background alerts/network | P@10 | P@25 | R@25 | R@50 | Account precision | Account recall | Latency median / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 777 | 0.385 | 3.809 | 0.574 | 0.200 | 0.160 | 0.067 | 0.133 | 0.385 | 0.549 | 2.070 / 4.120 |
| B1_centrality | 6602 | 0.027 | 32.363 | 28.873 | 0.000 | 0.000 | 0.000 | 0.000 | 0.027 | 0.327 | 3.770 / 6.300 |
| B2_static_rules | 984 | 0.355 | 4.824 | 0.912 | 0.000 | 0.000 | 0.000 | 0.167 | 0.355 | 0.640 | 2.600 / 5.830 |
| B3_v1_structural_only | 1082 | 0.084 | 5.304 | 4.270 | 0.000 | 0.000 | 0.000 | 0.000 | 0.072 | 0.710 | 9.380 / 21.960 |
| B4_v1_structural_temporal | 234 | 0.252 | 1.147 | 0.603 | 0.000 | 0.240 | 0.100 | 0.267 | 0.169 | 0.470 | 7.560 / 29.570 |
| B5_v2_full | 191 | 0.513 | 0.936 | 0.206 | 0.500 | 0.320 | 0.133 | 0.367 | 0.379 | 0.727 | 13.880 / 47.180 |

### By family (detection rate for suspicious, false-positive rate for benign)

| Family | B0_volume | B1_centrality | B2_static_rules | B3_v1_structural_only | B4_v1_structural_temporal | B5_v2_full |
|---|---|---|---|---|---|---|
| H1_crowdfunding | 0.750 | 1.000 | 0.833 | 1.000 | 1.000 | 1.000 |
| H2_microfinance_hub | 1.000 | 1.000 | 1.000 | 1.000 | 0.167 | 0.083 |
| H3_tight_supplier_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.917 |
| H4_reverse_chronology_chain | 0.667 | 0.917 | 0.917 | 1.000 | 0.000 | 0.000 |
| H5_payout_sweep | 1.000 | 0.667 | 0.917 | 0.333 | 0.250 | 1.000 |
| H6_reciprocal_trading | 1.000 | 1.000 | 1.000 | 0.250 | 0.167 | 0.000 |
| N1_merchant_settlement | 1.000 | 1.000 | 0.833 | 1.000 | 1.000 | 0.250 |
| N2_payroll | 1.000 | 0.917 | 1.000 | 0.250 | 0.000 | 0.000 |
| N3_supplier_payments | 1.000 | 1.000 | 1.000 | 0.750 | 0.083 | 0.167 |
| N4_family_remittance | 0.333 | 0.417 | 0.333 | 0.333 | 0.250 | 0.250 |
| N5_group_reimbursement | 0.000 | 0.833 | 0.000 | 0.750 | 0.083 | 0.083 |
| N6_loan_repayment | 0.667 | 1.000 | 0.667 | 0.250 | 0.000 | 0.000 |
| P1_mule_collection | 1.000 | 1.000 | 0.833 | 1.000 | 0.833 | 0.833 |
| P2_layering_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| P3_coordinated_distribution | 1.000 | 0.917 | 1.000 | 0.417 | 0.250 | 0.750 |
| P4_circular_transfers | 0.917 | 1.000 | 0.750 | 0.667 | 0.667 | 1.000 |
| P5_split_coordinated | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 | 0.917 |

## Split `val`

### Scenario unit (primary)

| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 36 | 86 | 4 | 10 | 0.295 [0.27, 0.32] | 0.900 [0.80, 0.97] | 0.445 | 0.896 | 0.100 |
| B1_centrality | 40 | 88 | 0 | 8 | 0.312 [0.30, 0.33] | 1.000 [1.00, 1.00] | 0.476 | 0.917 | 0.000 |
| B2_static_rules | 35 | 80 | 5 | 16 | 0.304 [0.27, 0.33] | 0.875 [0.78, 0.97] | 0.452 | 0.833 | 0.125 |
| B3_v1_structural_only | 31 | 66 | 9 | 30 | 0.320 [0.27, 0.37] | 0.775 [0.65, 0.90] | 0.453 | 0.688 | 0.225 |
| B4_v1_structural_temporal | 24 | 34 | 16 | 62 | 0.414 [0.33, 0.51] | 0.600 [0.45, 0.75] | 0.490 | 0.354 | 0.400 |
| B5_v2_full | 33 | 29 | 7 | 67 | 0.532 [0.46, 0.63] | 0.825 [0.70, 0.93] | 0.647 | 0.302 | 0.175 |

### Alert queue, alert and account units

| Method | Alerts | Alert precision | Alerts/network | Background alerts/network | P@10 | P@25 | R@25 | R@50 | Account precision | Account recall | Latency median / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 493 | 0.359 | 3.625 | 0.507 | 0.300 | 0.120 | 0.075 | 0.150 | 0.359 | 0.449 | 1.880 / 4.630 |
| B1_centrality | 4527 | 0.026 | 33.287 | 29.956 | 0.000 | 0.000 | 0.000 | 0.000 | 0.026 | 0.294 | 4.100 / 7.640 |
| B2_static_rules | 647 | 0.340 | 4.757 | 0.882 | 0.000 | 0.000 | 0.000 | 0.175 | 0.340 | 0.558 | 3.260 / 6.500 |
| B3_v1_structural_only | 763 | 0.058 | 5.610 | 4.618 | 0.000 | 0.000 | 0.000 | 0.000 | 0.060 | 0.574 | 9.510 / 44.360 |
| B4_v1_structural_temporal | 156 | 0.199 | 1.147 | 0.654 | 0.100 | 0.280 | 0.175 | 0.225 | 0.152 | 0.411 | 9.790 / 28.760 |
| B5_v2_full | 112 | 0.464 | 0.824 | 0.206 | 0.600 | 0.520 | 0.325 | 0.625 | 0.385 | 0.662 | 14.740 / 39.850 |

### By family (detection rate for suspicious, false-positive rate for benign)

| Family | B0_volume | B1_centrality | B2_static_rules | B3_v1_structural_only | B4_v1_structural_temporal | B5_v2_full |
|---|---|---|---|---|---|---|
| H1_crowdfunding | 1.000 | 1.000 | 0.875 | 1.000 | 1.000 | 1.000 |
| H2_microfinance_hub | 1.000 | 1.000 | 1.000 | 1.000 | 0.125 | 0.125 |
| H3_tight_supplier_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.875 |
| H4_reverse_chronology_chain | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 | 0.000 |
| H5_payout_sweep | 1.000 | 0.875 | 1.000 | 0.375 | 0.250 | 1.000 |
| H6_reciprocal_trading | 1.000 | 1.000 | 1.000 | 0.750 | 0.375 | 0.250 |
| N1_merchant_settlement | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 | 0.000 |
| N2_payroll | 1.000 | 1.000 | 1.000 | 0.375 | 0.000 | 0.000 |
| N3_supplier_payments | 1.000 | 1.000 | 1.000 | 0.625 | 0.000 | 0.000 |
| N4_family_remittance | 0.625 | 0.375 | 0.375 | 0.375 | 0.125 | 0.125 |
| N5_group_reimbursement | 0.125 | 0.750 | 0.000 | 0.375 | 0.375 | 0.250 |
| N6_loan_repayment | 1.000 | 1.000 | 1.000 | 0.375 | 0.000 | 0.000 |
| P1_mule_collection | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 | 0.750 |
| P2_layering_chain | 0.500 | 1.000 | 0.625 | 1.000 | 1.000 | 0.750 |
| P3_coordinated_distribution | 1.000 | 1.000 | 1.000 | 0.375 | 0.375 | 0.875 |
| P4_circular_transfers | 1.000 | 1.000 | 0.750 | 0.500 | 0.500 | 1.000 |
| P5_split_coordinated | 1.000 | 1.000 | 1.000 | 1.000 | 0.375 | 0.750 |

## Split `test`

### Scenario unit (primary)

| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 57 | 117 | 3 | 27 | 0.328 [0.31, 0.35] | 0.950 [0.88, 1.00] | 0.487 | 0.812 | 0.050 |
| B1_centrality | 58 | 127 | 2 | 17 | 0.314 [0.30, 0.33] | 0.967 [0.92, 1.00] | 0.473 | 0.882 | 0.033 |
| B2_static_rules | 53 | 112 | 7 | 32 | 0.321 [0.29, 0.35] | 0.883 [0.80, 0.97] | 0.471 | 0.778 | 0.117 |
| B3_v1_structural_only | 44 | 93 | 16 | 51 | 0.321 [0.28, 0.37] | 0.733 [0.62, 0.85] | 0.447 | 0.646 | 0.267 |
| B4_v1_structural_temporal | 32 | 42 | 28 | 102 | 0.432 [0.35, 0.52] | 0.533 [0.42, 0.67] | 0.478 | 0.292 | 0.467 |
| B5_v2_full | 49 | 38 | 11 | 106 | 0.563 [0.49, 0.64] | 0.817 [0.72, 0.92] | 0.667 | 0.264 | 0.183 |

### Alert queue, alert and account units

| Method | Alerts | Alert precision | Alerts/network | Background alerts/network | P@10 | P@25 | R@25 | R@50 | Account precision | Account recall | Latency median / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 746 | 0.369 | 3.657 | 0.564 | 0.500 | 0.240 | 0.100 | 0.133 | 0.369 | 0.497 | 1.970 / 4.780 |
| B1_centrality | 6540 | 0.026 | 32.059 | 28.794 | 0.000 | 0.000 | 0.000 | 0.000 | 0.026 | 0.306 | 3.940 / 7.350 |
| B2_static_rules | 935 | 0.370 | 4.583 | 0.799 | 0.000 | 0.000 | 0.000 | 0.183 | 0.370 | 0.626 | 3.460 / 7.540 |
| B3_v1_structural_only | 1157 | 0.055 | 5.672 | 4.833 | 0.000 | 0.000 | 0.000 | 0.000 | 0.059 | 0.608 | 10.010 / 23.750 |
| B4_v1_structural_temporal | 227 | 0.203 | 1.113 | 0.672 | 0.000 | 0.240 | 0.100 | 0.233 | 0.152 | 0.441 | 10.150 / 24.180 |
| B5_v2_full | 158 | 0.481 | 0.775 | 0.196 | 0.500 | 0.400 | 0.167 | 0.317 | 0.366 | 0.640 | 14.540 / 44.670 |

### By family (detection rate for suspicious, false-positive rate for benign)

| Family | B0_volume | B1_centrality | B2_static_rules | B3_v1_structural_only | B4_v1_structural_temporal | B5_v2_full |
|---|---|---|---|---|---|---|
| H1_crowdfunding | 0.833 | 1.000 | 0.750 | 1.000 | 1.000 | 1.000 |
| H2_microfinance_hub | 1.000 | 1.000 | 1.000 | 1.000 | 0.083 | 0.083 |
| H3_tight_supplier_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| H4_reverse_chronology_chain | 0.667 | 0.833 | 0.667 | 1.000 | 0.000 | 0.000 |
| H5_payout_sweep | 1.000 | 0.833 | 0.917 | 0.417 | 0.250 | 1.000 |
| H6_reciprocal_trading | 1.000 | 1.000 | 0.917 | 0.417 | 0.167 | 0.000 |
| N1_merchant_settlement | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| N2_payroll | 1.000 | 0.833 | 1.000 | 0.083 | 0.000 | 0.000 |
| N3_supplier_payments | 1.000 | 0.917 | 1.000 | 0.750 | 0.000 | 0.083 |
| N4_family_remittance | 0.583 | 0.417 | 0.500 | 0.333 | 0.000 | 0.000 |
| N5_group_reimbursement | 0.000 | 0.750 | 0.000 | 0.417 | 0.000 | 0.000 |
| N6_loan_repayment | 0.667 | 1.000 | 0.583 | 0.333 | 0.000 | 0.000 |
| P1_mule_collection | 1.000 | 1.000 | 0.917 | 1.000 | 0.667 | 0.667 |
| P2_layering_chain | 0.750 | 1.000 | 0.750 | 1.000 | 1.000 | 0.917 |
| P3_coordinated_distribution | 1.000 | 0.833 | 1.000 | 0.333 | 0.250 | 0.583 |
| P4_circular_transfers | 1.000 | 1.000 | 0.750 | 0.333 | 0.333 | 1.000 |
| P5_split_coordinated | 1.000 | 1.000 | 1.000 | 1.000 | 0.417 | 0.917 |

## Time to detection (simulated days)

* `dev` B3_v1_structural_only: median 2 d, max 7 d over 49 detected networks (11 not detected on the full window, 0 of them alerted transiently mid-replay)
* `dev` B4_v1_structural_temporal: median 2 d, max 8 d over 39 detected networks (21 not detected on the full window, 4 of them alerted transiently mid-replay)
* `dev` B5_v2_full: median 2 d, max 13 d over 54 detected networks (6 not detected on the full window, 1 of them alerted transiently mid-replay)
* `val` B3_v1_structural_only: median 2 d, max 12 d over 31 detected networks (9 not detected on the full window, 0 of them alerted transiently mid-replay)
* `val` B4_v1_structural_temporal: median 2 d, max 12 d over 24 detected networks (16 not detected on the full window, 2 of them alerted transiently mid-replay)
* `val` B5_v2_full: median 2 d, max 13 d over 33 detected networks (7 not detected on the full window, 3 of them alerted transiently mid-replay)
* `test` B3_v1_structural_only: median 2 d, max 6 d over 44 detected networks (16 not detected on the full window, 0 of them alerted transiently mid-replay)
* `test` B4_v1_structural_temporal: median 3 d, max 8 d over 32 detected networks (28 not detected on the full window, 1 of them alerted transiently mid-replay)
* `test` B5_v2_full: median 3 d, max 11 d over 49 detected networks (11 not detected on the full window, 2 of them alerted transiently mid-replay)

## Ablations

| Experiment | Split | Precision | Recall | F1 | FPR | Alerts/network | Changed outcomes | Outcome transitions | Band changes |
|---|---|---|---|---|---|---|---|---|---|
| full_v2_reference | test | 0.563 | 0.817 | 0.667 | 0.264 | 0.775 | 0 | — | — |
| no_temporal_corroboration | test | 0.333 | 0.567 | 0.420 | 0.472 | 2.662 | 69 | H2_microfinance_hub: TN->FP x11, H3_tight_supplier_chain: FP->TN x11, H4_reverse_chronology_chain: TN->FP x2, N2_payroll: TN->FP x12, N3_supplier_payments: TN->FP x3, N4_family_remittance: TN->FP x10, N6_loan_repayment: TN->FP x3, P2_layering_chain: FN->TP x1, P2_layering_chain: TP->FN x4, P4_circular_transfers: TP->FN x12 | high->low x34, high->medium x66, low->medium x443, medium->low x24 |
| no_fungibility_attribution | test | 0.568 | 0.833 | 0.676 | 0.264 | 1.172 | 1 | P2_layering_chain: FN->TP x1 | low->high x25, low->medium x56, medium->high x5 |
| no_benign_context | test | 0.485 | 0.817 | 0.609 | 0.361 | 0.863 | 14 | H6_reciprocal_trading: TN->FP x2, N1_merchant_settlement: TN->FP x12 | low->high x14, low->medium x4, medium->high x4 |
| no_coverage_safeguards | test | 0.591 | 0.917 | 0.719 | 0.264 | 0.824 | 6 | P1_mule_collection: FN->TP x3, P3_coordinated_distribution: FN->TP x3 | insufficient_evidence->low x11, insufficient_evidence->medium x10 |
| no_dedication_strength | test | 0.570 | 0.817 | 0.671 | 0.257 | 0.716 | 3 | N3_supplier_payments: FP->TN x1, P5_split_coordinated: FN->TP x1, P5_split_coordinated: TP->FN x1 | high->medium x7, low->medium x2, medium->low x14 |
| no_funnel_detector | test | 0.617 | 0.617 | 0.617 | 0.160 | 0.417 | 27 | H1_crowdfunding: FP->TN x12, H2_microfinance_hub: FP->TN x1, H3_tight_supplier_chain: FP->TN x1, N3_supplier_payments: FP->TN x1, P1_mule_collection: TP->FN x8, P5_split_coordinated: TP->FN x4 | formations_only_in_reference x866 |
| no_chain_detector | test | 0.576 | 0.633 | 0.603 | 0.194 | 0.574 | 21 | H3_tight_supplier_chain: FP->TN x10, P2_layering_chain: TP->FN x11 | formations_only_in_reference x291 |
| no_fanout_detector | test | 0.597 | 0.717 | 0.651 | 0.201 | 0.618 | 15 | H5_payout_sweep: FP->TN x9, P3_coordinated_distribution: TP->FN x3, P5_split_coordinated: TP->FN x3 | formations_only_in_reference x146 |
| no_cycle_detector | test | 0.519 | 0.683 | 0.590 | 0.264 | 0.716 | 8 | P4_circular_transfers: TP->FN x8 | formations_only_in_reference x3526 |
| thresholds_minus_20pct | test | 0.532 | 0.833 | 0.649 | 0.306 | 1.225 | 7 | H2_microfinance_hub: TN->FP x2, N3_supplier_payments: TN->FP x3, N4_family_remittance: TN->FP x1, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x1496, formations_only_in_reference x417, low->high x6, low->medium x20, medium->high x2 |
| thresholds_plus_20pct | test | 0.580 | 0.783 | 0.667 | 0.236 | 0.608 | 6 | H2_microfinance_hub: FP->TN x1, H3_tight_supplier_chain: FP->TN x2, N3_supplier_payments: FP->TN x1, P2_layering_chain: TP->FN x1, P5_split_coordinated: TP->FN x1 | formations_only_in_experiment x257, formations_only_in_reference x1271, high->low x6, high->medium x4, medium->low x9 |

## Robustness

| Experiment | Split | Precision | Recall | F1 | FPR | Alerts/network | Changed outcomes | Outcome transitions | Band changes |
|---|---|---|---|---|---|---|---|---|---|
| missing_edges_10pct [B5_v2_full] | test | 0.575 | 0.767 | 0.657 | 0.236 | 0.740 | 11 | H3_tight_supplier_chain: FP->TN x4, N3_supplier_payments: FP->TN x1, N4_family_remittance: TN->FP x1, P2_layering_chain: FN->TP x1, P2_layering_chain: TP->FN x1, P4_circular_transfers: TP->FN x3 | formations_only_in_experiment x610, formations_only_in_reference x1660, high->low x5, high->medium x2, low->high x2, low->medium x2, medium->high x2, medium->low x3 |
| missing_edges_10pct [B4_v1_structural_temporal] | test | 0.457 | 0.533 | 0.492 | 0.264 | 1.044 | 8 | H3_tight_supplier_chain: FP->TN x4, H6_reciprocal_trading: FP->TN x1, N4_family_remittance: TN->FP x1, P2_layering_chain: TP->FN x1, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x542, formations_only_in_reference x582, high->low x2, high->medium x5, low->high x2, low->medium x1, medium->high x1, medium->low x7 |
| missing_edges_25pct [B5_v2_full] | test | 0.529 | 0.600 | 0.562 | 0.222 | 0.750 | 31 | H2_microfinance_hub: FP->TN x1, H3_tight_supplier_chain: FP->TN x7, H5_payout_sweep: FP->TN x2, N1_merchant_settlement: TN->FP x3, N3_supplier_payments: FP->TN x1, N3_supplier_payments: TN->FP x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x2, P2_layering_chain: TP->FN x6, P4_circular_transfers: TP->FN x6, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x960, formations_only_in_reference x3062, high->low x12, high->medium x5, low->high x1, low->medium x8, medium->high x2, medium->low x5 |
| missing_edges_25pct [B4_v1_structural_temporal] | test | 0.431 | 0.367 | 0.396 | 0.201 | 0.779 | 29 | H2_microfinance_hub: FP->TN x1, H3_tight_supplier_chain: FP->TN x9, H5_payout_sweep: FP->TN x3, H6_reciprocal_trading: FP->TN x2, N3_supplier_payments: TN->FP x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x2, P2_layering_chain: TP->FN x7, P4_circular_transfers: TP->FN x2, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x867, formations_only_in_reference x874, high->low x10, high->medium x2, low->high x1, low->medium x1, medium->low x10 |
| missing_timestamps [B5_v2_full] | test | 0.563 | 0.817 | 0.667 | 0.264 | 0.784 | 0 | — | high->low x1, high->medium x15, low->medium x3 |
| missing_timestamps [B4_v1_structural_temporal] | test | 0.432 | 0.533 | 0.478 | 0.292 | 1.132 | 0 | — | high->medium x14, low->medium x4 |
| duplicate_rows [B5_v2_full] | test | 0.563 | 0.817 | 0.667 | 0.264 | 0.775 | 0 | — | — |
| duplicate_rows [B4_v1_structural_temporal] | test | 0.432 | 0.533 | 0.478 | 0.292 | 1.113 | 0 | — | — |
| double_posting [B5_v2_full] | test | 0.551 | 0.817 | 0.658 | 0.278 | 0.824 | 2 | H6_reciprocal_trading: TN->FP x1, N4_family_remittance: TN->FP x1 | formations_only_in_experiment x270, formations_only_in_reference x148, high->low x1, high->medium x6, low->high x4, low->medium x8 |
| double_posting [B4_v1_structural_temporal] | test | 0.429 | 0.550 | 0.482 | 0.306 | 1.176 | 3 | H2_microfinance_hub: TN->FP x1, N4_family_remittance: TN->FP x1, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x135, formations_only_in_reference x139, high->low x2, high->medium x5, low->high x8, low->medium x12, medium->low x2 |
| out_of_order_ingestion [B5_v2_full] | test | 0.563 | 0.817 | 0.667 | 0.264 | 0.775 | 0 | — | — |
| out_of_order_ingestion [B4_v1_structural_temporal] | test | 0.432 | 0.533 | 0.478 | 0.292 | 1.113 | 0 | — | — |
| larger_benign_volume [B5_v2_full] | test | 0.570 | 0.817 | 0.671 | 0.257 | 0.931 | 5 | H3_tight_supplier_chain: FP->TN x2, N3_supplier_payments: TN->FP x1, P2_layering_chain: FN->TP x1, P5_split_coordinated: TP->FN x1 | formations_only_in_experiment x25082, formations_only_in_reference x1140, high->medium x1, low->high x5, low->medium x6, medium->low x6 |
| larger_benign_volume [B4_v1_structural_temporal] | test | 0.408 | 0.483 | 0.443 | 0.292 | 2.196 | 7 | H3_tight_supplier_chain: FP->TN x2, H6_reciprocal_trading: TN->FP x2, P5_split_coordinated: TP->FN x3 | formations_only_in_experiment x947, formations_only_in_reference x447, low->high x7, low->medium x6, medium->high x2, medium->low x4 |
| partial_window_first_60pct [B5_v2_full] | test | 0.581 | 0.717 | 0.642 | 0.215 | 0.775 | 25 | H1_crowdfunding: FP->TN x2, H2_microfinance_hub: TN->FP x1, H3_tight_supplier_chain: FP->TN x7, H5_payout_sweep: FP->TN x3, N1_merchant_settlement: TN->FP x4, N3_supplier_payments: FP->TN x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x1, P3_coordinated_distribution: TP->FN x3, P5_split_coordinated: TP->FN x2 | formations_only_in_experiment x965, formations_only_in_reference x3778, high->low x5, high->medium x3, low->high x1, low->medium x11, medium->high x3, medium->low x1 |
| partial_window_first_60pct [B4_v1_structural_temporal] | test | 0.484 | 0.500 | 0.492 | 0.222 | 0.922 | 20 | H1_crowdfunding: FP->TN x2, H2_microfinance_hub: TN->FP x1, H3_tight_supplier_chain: FP->TN x8, H5_payout_sweep: FP->TN x1, H6_reciprocal_trading: FP->TN x2, H6_reciprocal_trading: TN->FP x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x2, P3_coordinated_distribution: TP->FN x1, P5_split_coordinated: FN->TP x1 | formations_only_in_experiment x913, formations_only_in_reference x994, high->low x3, low->high x1, medium->low x4 |
| partial_window_last_60pct [B5_v2_full] | test | 0.415 | 0.367 | 0.389 | 0.215 | 0.760 | 60 | H1_crowdfunding: FP->TN x8, H2_microfinance_hub: FP->TN x1, H2_microfinance_hub: TN->FP x2, H3_tight_supplier_chain: FP->TN x4, H5_payout_sweep: FP->TN x4, H6_reciprocal_trading: TN->FP x2, N1_merchant_settlement: TN->FP x5, N3_supplier_payments: FP->TN x1, N3_supplier_payments: TN->FP x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x3, P2_layering_chain: FN->TP x1, P2_layering_chain: TP->FN x10, P3_coordinated_distribution: FN->TP x1, P3_coordinated_distribution: TP->FN x3, P4_circular_transfers: TP->FN x9, P5_split_coordinated: TP->FN x4 | formations_only_in_experiment x933, formations_only_in_reference x3963, high->low x2, low->high x2, low->medium x7, medium->low x1 |
| partial_window_last_60pct [B4_v1_structural_temporal] | test | 0.348 | 0.267 | 0.302 | 0.208 | 0.887 | 46 | H1_crowdfunding: FP->TN x8, H2_microfinance_hub: FP->TN x1, H2_microfinance_hub: TN->FP x2, H3_tight_supplier_chain: FP->TN x4, H5_payout_sweep: FP->TN x3, H6_reciprocal_trading: FP->TN x2, H6_reciprocal_trading: TN->FP x2, N3_supplier_payments: TN->FP x1, N4_family_remittance: TN->FP x1, P1_mule_collection: TP->FN x3, P2_layering_chain: TP->FN x10, P3_coordinated_distribution: FN->TP x1, P3_coordinated_distribution: TP->FN x1, P4_circular_transfers: TP->FN x2, P5_split_coordinated: FN->TP x2, P5_split_coordinated: TP->FN x3 | formations_only_in_experiment x879, formations_only_in_reference x1031, low->high x1, low->medium x3, medium->high x1 |

## Scale test (all networks of the split merged into one dataset)

| Method | Transactions | Accounts | Formations | Wall time s | Partial |
|---|---|---|---|---|---|
| B5_v2_full | 55157 | 14549 | 1803 | 32.7 | cycle_budget_exceeded:KZT |
| B4_v1 | 55157 | 14549 | 1157 | 15.65 | no |
