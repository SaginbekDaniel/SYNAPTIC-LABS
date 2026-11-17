# Licence matrix

Licence is a hard gate, separate from technical score. **No source code from any repository below was copied
into NEXORA.** Every adopted idea was re-implemented independently (see `ADOPTION_DECISIONS.md`).

| Repository | Commit audited | Licence (file in repo) | Reuse of code permitted? | Decision |
|---|---|---|---|---|
| BAITC-Hacks/hack-7bb3c2d4-vantage-ai | `577955132c12` | **none found** | No (all rights reserved by default) | Ideas only |
| BAITC-Hacks/hack-c41412b2-unru-ai | `10eb258584c0` | **none found** | No | Ideas only |
| BAITC-Hacks/hack-0ace0672-natural-intelligence | `e6f701f6546b` | **none found** | No | Ideas only |
| BAITC-Hacks/hack-e3bf6094-jigas | `bfaed6263549` | **none found** (bundles cytoscape/vis-network licences) | No | Ideas only |
| BAITC-Hacks/hack-082c1388-moggers | `7834d4340d68` | **none found** | No | Not used |
| BAITC-Hacks/hack-173e8652-synex | `e972af30e4f8` | **none found** | No | Ideas only |
| IBM/AMLSim | `7338a4bcb1af` | Apache-2.0 | Yes, with NOTICE + change notes | Ideas only (typology vocabulary) |
| SantanderAI/gen-fraud-graph | `8665b9ec44de` | Apache-2.0 (NOTICE file present) | Yes, with NOTICE | Ideas only (decoy negatives, ring-level metric) |
| farishaddad/fraud-synth | `0cbb87033d3b` | MIT | Yes, with copyright notice | Not used |
| masenka31/fraud-benchmark | `71027c6649a8` | MIT | Yes, with copyright notice | Ideas only (methodology) |
| Fraud-Detection-Handbook | `81cf7d1714bb` | Code GPL-3.0; prose separate | Copyleft: would force GPL on NEXORA | Ideas only (top-k metrics); no code |
| sofeikov/ezrules | `0e0092fdd389` | Apache-2.0 | Yes | Ideas only (shadow evaluation) |
| blnkfinance/watch | `d3a1db187fbe` | Apache-2.0 | Yes | Ideas only (B1 rule shapes) |
| xendit/xendit-marble | `bc115c6f97d5` | Elastic License 2.0 | Restricted (no managed-service offering) | Not used |
| checkmarble/marble | `236c290718a7` | Elastic License 2.0 | Restricted | Not used |
| Atrangi-Coders/Financial-Forensics-Engine | `1155c5481cfe` | MIT | Yes | Rejected as design (see REJECTED_APPROACHES) |
| IBM/Multi-GNN | `252b0252afca` | Apache-2.0 | Yes | Not adopted (GNN track rejected for MVP) |
| lidonmiguel/signalgraph-aml | `c370225a75c3` | MIT | Yes | Ideas only (fixed investigation budget framing) |
| jube-home/aml-fraud-transaction-monitoring | `01c4afdbcdb1` | AGPL-3.0 | Copyleft (network use) | Not used |
| safe-graph/DGFraud | `22b72d75f81d` | Apache-2.0 | Yes | Not used |

Datasets: no external dataset was downloaded or redistributed. The historical challenge parquet files present in
several BAITC repositories were **not** used. All NEXORA data is produced by `nexora.evaluation.generator`.
