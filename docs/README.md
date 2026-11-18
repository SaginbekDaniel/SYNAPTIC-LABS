# NEXORA documentation

| Area | Document | Contents |
|---|---|---|
| Overview | [../README.md](../README.md) | What NEXORA is, features, evaluation summary, quick start |
| Architecture | [architecture/system.md](architecture/system.md) | Diagrams: components, ingestion, analysis jobs, case lifecycle |
| | [ARCHITECTURE.md](ARCHITECTURE.md) | Package rules, analysis pipeline, persistence guarantees, worker semantics |
| | [INTERFACES.md](INTERFACES.md) | Contracts between modules and the HTTP API |
| | [ADR/0001-decisions.md](ADR/0001-decisions.md) | Architecture decision records |
| | [PROVENANCE.md](PROVENANCE.md) | Where evidence comes from and how it is verified |
| Deployment | [deployment/railway.md](deployment/railway.md) | Railway topology, setup, variables, security model, operations, cost, troubleshooting |
| Development | [development/local-setup.md](development/local-setup.md) | Docker Compose and hot-reload setups, common problems |
| | [development/testing.md](development/testing.md) | Test layers, commands, smoke test |
| | [../CONTRIBUTING.md](../CONTRIBUTING.md) | Project rules and workflow |
| Evaluation | [EVALUATION.md](EVALUATION.md) | `bench-v1` results (generated — do not edit) |
| | [LIMITATIONS.md](LIMITATIONS.md) | What does not work, measured |
| | [TEST_REPORT.md](TEST_REPORT.md) | Gate results per development session |
| Design | [design/DESIGN_DIRECTION.md](design/DESIGN_DIRECTION.md) | NEXORA Dark Intelligence design direction, components, UX review |
| Research | [research/GITHUB_LANDSCAPE.md](research/GITHUB_LANDSCAPE.md) | Prior art, audits, adoption and rejection decisions, licences |
| Planning | [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) · [REFERENCE_AUDIT.md](REFERENCE_AUDIT.md) | Stage status, reference audit |
| Security | [../SECURITY.md](../SECURITY.md) | Controls, known gaps, private reporting |

Screenshots used in the README live in [assets/screenshots/](assets/screenshots/) and are
captured from the production build on synthetic data.
