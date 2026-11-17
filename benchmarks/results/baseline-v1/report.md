# Benchmark report — baseline-v1

> SYNTHETIC BENCHMARK. All networks, labels and metrics come from the NEXORA synthetic scenario generator, not from bank data. Results describe behaviour on this synthetic distribution only and are not estimates of real-world fraud detection accuracy.

* Benchmark: `nexora-bench-v1`, master seed `2026`
* Code: `8430dcfadae8094ab65a2992c25204574941db31`
* Created: 2026-11-17T06:16:18+00:00 · duration 38.4 s
* Host: Intel(R) Xeon(R) Processor @ 2.10GHz · Python 3.13.18 · networkx 3.7
* Splits evaluated: dev, val

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

## Split `dev`

### Scenario unit (primary)

| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 59 | 113 | 1 | 31 | 0.343 [0.32, 0.36] | 0.983 [0.95, 1.00] | 0.509 | 0.785 | 0.017 |
| B1_centrality | 59 | 129 | 1 | 15 | 0.314 [0.30, 0.33] | 0.983 [0.95, 1.00] | 0.476 | 0.896 | 0.017 |
| B2_static_rules | 55 | 114 | 5 | 30 | 0.325 [0.30, 0.35] | 0.917 [0.83, 0.98] | 0.480 | 0.792 | 0.083 |
| B3_v1_structural_only | 49 | 95 | 11 | 49 | 0.340 [0.30, 0.38] | 0.817 [0.72, 0.92] | 0.480 | 0.660 | 0.183 |
| B4_v1_structural_temporal | 39 | 48 | 21 | 96 | 0.448 [0.37, 0.52] | 0.650 [0.53, 0.77] | 0.531 | 0.333 | 0.350 |

### Alert queue, alert and account units

| Method | Alerts | Alert precision | Alerts/network | Background alerts/network | P@10 | P@25 | R@25 | R@50 | Account precision | Account recall | Latency median / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 777 | 0.385 | 3.809 | 0.574 | 0.200 | 0.160 | 0.067 | 0.133 | 0.385 | 0.549 | 1.660 / 3.050 |
| B1_centrality | 6602 | 0.027 | 32.363 | 28.873 | 0.000 | 0.000 | 0.000 | 0.000 | 0.027 | 0.327 | 3.380 / 5.670 |
| B2_static_rules | 984 | 0.355 | 4.824 | 0.912 | 0.000 | 0.000 | 0.000 | 0.167 | 0.355 | 0.640 | 2.660 / 5.720 |
| B3_v1_structural_only | 1082 | 0.084 | 5.304 | 4.270 | 0.000 | 0.000 | 0.000 | 0.000 | 0.072 | 0.710 | 8.790 / 26.040 |
| B4_v1_structural_temporal | 234 | 0.252 | 1.147 | 0.603 | 0.000 | 0.240 | 0.100 | 0.267 | 0.169 | 0.470 | 9.460 / 38.920 |

### By family (detection rate for suspicious, false-positive rate for benign)

| Family | B0_volume | B1_centrality | B2_static_rules | B3_v1_structural_only | B4_v1_structural_temporal |
|---|---|---|---|---|---|
| H1_crowdfunding | 0.750 | 1.000 | 0.833 | 1.000 | 1.000 |
| H2_microfinance_hub | 1.000 | 1.000 | 1.000 | 1.000 | 0.167 |
| H3_tight_supplier_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| H4_reverse_chronology_chain | 0.667 | 0.917 | 0.917 | 1.000 | 0.000 |
| H5_payout_sweep | 1.000 | 0.667 | 0.917 | 0.333 | 0.250 |
| H6_reciprocal_trading | 1.000 | 1.000 | 1.000 | 0.250 | 0.167 |
| N1_merchant_settlement | 1.000 | 1.000 | 0.833 | 1.000 | 1.000 |
| N2_payroll | 1.000 | 0.917 | 1.000 | 0.250 | 0.000 |
| N3_supplier_payments | 1.000 | 1.000 | 1.000 | 0.750 | 0.083 |
| N4_family_remittance | 0.333 | 0.417 | 0.333 | 0.333 | 0.250 |
| N5_group_reimbursement | 0.000 | 0.833 | 0.000 | 0.750 | 0.083 |
| N6_loan_repayment | 0.667 | 1.000 | 0.667 | 0.250 | 0.000 |
| P1_mule_collection | 1.000 | 1.000 | 0.833 | 1.000 | 0.833 |
| P2_layering_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| P3_coordinated_distribution | 1.000 | 0.917 | 1.000 | 0.417 | 0.250 |
| P4_circular_transfers | 0.917 | 1.000 | 0.750 | 0.667 | 0.667 |
| P5_split_coordinated | 1.000 | 1.000 | 1.000 | 1.000 | 0.500 |

## Split `val`

### Scenario unit (primary)

| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |
|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 36 | 86 | 4 | 10 | 0.295 [0.27, 0.32] | 0.900 [0.80, 0.97] | 0.445 | 0.896 | 0.100 |
| B1_centrality | 40 | 88 | 0 | 8 | 0.312 [0.30, 0.33] | 1.000 [1.00, 1.00] | 0.476 | 0.917 | 0.000 |
| B2_static_rules | 35 | 80 | 5 | 16 | 0.304 [0.27, 0.33] | 0.875 [0.78, 0.97] | 0.452 | 0.833 | 0.125 |
| B3_v1_structural_only | 31 | 66 | 9 | 30 | 0.320 [0.27, 0.37] | 0.775 [0.65, 0.90] | 0.453 | 0.688 | 0.225 |
| B4_v1_structural_temporal | 24 | 34 | 16 | 62 | 0.414 [0.33, 0.51] | 0.600 [0.45, 0.75] | 0.490 | 0.354 | 0.400 |

### Alert queue, alert and account units

| Method | Alerts | Alert precision | Alerts/network | Background alerts/network | P@10 | P@25 | R@25 | R@50 | Account precision | Account recall | Latency median / p95 ms |
|---|---|---|---|---|---|---|---|---|---|---|---|
| B0_volume | 493 | 0.359 | 3.625 | 0.507 | 0.300 | 0.120 | 0.075 | 0.150 | 0.359 | 0.449 | 2.160 / 4.180 |
| B1_centrality | 4527 | 0.026 | 33.287 | 29.956 | 0.000 | 0.000 | 0.000 | 0.000 | 0.026 | 0.294 | 3.960 / 7.210 |
| B2_static_rules | 647 | 0.340 | 4.757 | 0.882 | 0.000 | 0.000 | 0.000 | 0.175 | 0.340 | 0.558 | 2.950 / 8.050 |
| B3_v1_structural_only | 763 | 0.058 | 5.610 | 4.618 | 0.000 | 0.000 | 0.000 | 0.000 | 0.060 | 0.574 | 8.750 / 34.900 |
| B4_v1_structural_temporal | 156 | 0.199 | 1.147 | 0.654 | 0.100 | 0.280 | 0.175 | 0.225 | 0.152 | 0.411 | 9.360 / 33.620 |

### By family (detection rate for suspicious, false-positive rate for benign)

| Family | B0_volume | B1_centrality | B2_static_rules | B3_v1_structural_only | B4_v1_structural_temporal |
|---|---|---|---|---|---|
| H1_crowdfunding | 1.000 | 1.000 | 0.875 | 1.000 | 1.000 |
| H2_microfinance_hub | 1.000 | 1.000 | 1.000 | 1.000 | 0.125 |
| H3_tight_supplier_chain | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| H4_reverse_chronology_chain | 1.000 | 1.000 | 1.000 | 1.000 | 0.000 |
| H5_payout_sweep | 1.000 | 0.875 | 1.000 | 0.375 | 0.250 |
| H6_reciprocal_trading | 1.000 | 1.000 | 1.000 | 0.750 | 0.375 |
| N1_merchant_settlement | 1.000 | 1.000 | 0.750 | 1.000 | 1.000 |
| N2_payroll | 1.000 | 1.000 | 1.000 | 0.375 | 0.000 |
| N3_supplier_payments | 1.000 | 1.000 | 1.000 | 0.625 | 0.000 |
| N4_family_remittance | 0.625 | 0.375 | 0.375 | 0.375 | 0.125 |
| N5_group_reimbursement | 0.125 | 0.750 | 0.000 | 0.375 | 0.375 |
| N6_loan_repayment | 1.000 | 1.000 | 1.000 | 0.375 | 0.000 |
| P1_mule_collection | 1.000 | 1.000 | 1.000 | 1.000 | 0.750 |
| P2_layering_chain | 0.500 | 1.000 | 0.625 | 1.000 | 1.000 |
| P3_coordinated_distribution | 1.000 | 1.000 | 1.000 | 0.375 | 0.375 |
| P4_circular_transfers | 1.000 | 1.000 | 0.750 | 0.500 | 0.500 |
| P5_split_coordinated | 1.000 | 1.000 | 1.000 | 1.000 | 0.375 |

## Time to detection (simulated days)

* `dev` B3_v1_structural_only: median 2 d, max 7 d over 49 detected networks (11 not detected on the full window, 0 of them alerted transiently mid-replay)
* `dev` B4_v1_structural_temporal: median 2 d, max 8 d over 39 detected networks (21 not detected on the full window, 4 of them alerted transiently mid-replay)
* `val` B3_v1_structural_only: median 2 d, max 12 d over 31 detected networks (9 not detected on the full window, 0 of them alerted transiently mid-replay)
* `val` B4_v1_structural_temporal: median 2 d, max 12 d over 24 detected networks (16 not detected on the full window, 2 of them alerted transiently mid-replay)
