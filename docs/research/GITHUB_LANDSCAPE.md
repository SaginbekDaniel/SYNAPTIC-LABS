# GitHub landscape (research date 2026-11-17)

## Access and method

* `github.com` web pages and `api.github.com` returned **HTTP 403** through this session's proxy; GitHub code
  search was therefore unavailable. **`git clone` over HTTPS worked**, so every repository below marked
  *cloned* was shallow-cloned (`--depth 1`, large blobs filtered) into an isolated scratch directory at the
  exact commit listed in `LICENSE_MATRIX.md`. Cloned code was **read, never executed**.
* Discovery: the spec's reference list (§4) plus three web searches (Firecrawl, restricted to github.com) for
  AML graph detection, temporal fan-in/fan-out/scatter-gather typologies and GNN fraud benchmarks. Search
  snippets are *documented* claims only.
* This supersedes `docs/REFERENCE_AUDIT.md`, which recorded that no reference was reachable in an earlier session.

## Candidates (35)

| # | Repository | Category | Status in this research |
|---|---|---|---|
| 1 | BAITC-Hacks/hack-7bb3c2d4-vantage-ai | Graph formations, completeness | cloned, deep audit |
| 2 | BAITC-Hacks/hack-c41412b2-unru-ai | Temporal flow, stability | cloned, deep audit |
| 3 | BAITC-Hacks/hack-0ace0672-natural-intelligence | Motifs, peer anomaly | cloned, deep audit |
| 4 | BAITC-Hacks/hack-e3bf6094-jigas | Contracts, deterministic reports | cloned, audit |
| 5 | BAITC-Hacks/hack-082c1388-moggers | React graph UI | cloned, audit |
| 6 | BAITC-Hacks/hack-173e8652-synex | Case workflow, LLM governance | cloned, audit |
| 7 | IBM/AMLSim | AML simulator / typologies | cloned, deep audit |
| 8 | SantanderAI/gen-fraud-graph | Fraud-ring generator, evaluation | cloned, deep audit |
| 9 | farishaddad/fraud-synth | Synthetic transaction generators | cloned, audit |
| 10 | masenka31/fraud-benchmark | Benchmark methodology, label delay | cloned, deep audit |
| 11 | Fraud-Detection-Handbook/fraud-detection-handbook | Metrics, validation | cloned, audit |
| 12 | sofeikov/ezrules | Rule lifecycle, shadow, backtest | cloned, deep audit |
| 13 | blnkfinance/watch | Rule DSL, monitoring | cloned, audit |
| 14 | xendit/xendit-marble | Decision engine (fork) | cloned, licence + layout |
| 15 | checkmarble/marble | Decision engine, case manager | cloned, licence + layout |
| 16 | Atrangi-Coders/Financial-Forensics-Engine | Mule-ring heuristics | cloned, deep audit |
| 17 | IBM/Multi-GNN | GNN for AML (AAAI 2024 / NeurIPS 2023) | cloned, audit |
| 18 | lidonmiguel/signalgraph-aml | Temporal motifs, capacity planning | cloned, audit |
| 19 | jube-home/aml-fraud-transaction-monitoring | Transaction monitoring platform | cloned, licence + layout |
| 20 | safe-graph/DGFraud | GNN fraud toolbox | cloned, licence + layout |
| 21 | safe-graph/graph-fraud-detection-papers | Paper list | discovered (search) |
| 22 | AI4Risk/awesome-graph-based-fraud-detection | Paper list | discovered |
| 23 | issacchan26/AntiMoneyLaunderingDetectionWithGNN | GAT for AML | discovered |
| 24 | mominalix/AI-Based-Anti-Money-Laundering-AML-System | AML platform | discovered |
| 25 | mwasifanwar/cryptograph | GNN, blockchain | discovered |
| 26 | Md-hayath/FinGuard-GNN-Fraud-Detection | GNN banking | discovered |
| 27 | SKR-35/Awesome-Financial-Crime | Tool list | discovered |
| 28 | NickyGuants/kenya_sacco_sim | Synthetic AML dataset | discovered |
| 29 | chenxi1228/Awesome-BehavioralData | Behavioural data survey | discovered |
| 30 | wdhyun/LEX-GNN | GNN (CIKM 2024) | discovered via paper list |
| 31 | xydong127/RQGNN | Graph-level anomaly (ICLR 2024) | discovered via paper list |
| 32 | split-gnn/splitgnn | Heterophily GNN (CIKM 2023) | discovered via paper list |
| 33 | TommyDzh/DIAM | Crypto illicit accounts | discovered via paper list |
| 34 | zjunet/AMNet | GNN anomaly (IJCAI 2022) | discovered via paper list |
| 35 | yzhao062 (PyOD) | Outlier-detection library | discovered |

Deep audits: `REPOSITORY_DEEP_AUDIT.md`. Scores: `REPOSITORY_SCORECARD.md`. Licences: `LICENSE_MATRIX.md`.
