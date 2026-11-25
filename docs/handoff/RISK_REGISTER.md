# Risk register

Live register of risks to correctness, security, delivery and credibility. It supersedes the short table in
MASTER_HANDOFF §22 (kept for history). Findings (`H-nn`) are in MASTER_HANDOFF §16; tasks (`B-nnn`) in
EXECUTION_BACKLOG.md. Likelihood/impact: L low · M medium · H high. Review at every session end.

| ID | Risk | L / I | Evidence | Mitigation (task) | Owner | Status |
|---|---|---|---|---|---|---|
| R-01 | Integration line never reaches the default branch; work keeps forking from a stale base | H / H | default branch still `ea5ca9c`; 54 commits only on `graph-workspace-wip`; a collaborator branched from the stale base (H-26) | one superseding PR (D-1, B-002) | owner | open |
| R-02 | Collaborator feature merged with a second auth mechanism | M / H | H-26 | B-056 after D-12; authorization matrix extended | owner + agent | open |
| R-03 | Migration collision at deploy | L / H | H-01; B-001 guard in CI | keep single head; never renumber `0001`–`0004` | agent | mitigated |
| R-04 | Tuning on a consumed test set → false confidence | M / H | sealed-v1 consumed (H-14); sealed-v2 0 of 3 uses spent | protocol-first (§12); adversarial dev suite first (B-045) | agent | mitigated |
| R-05 | Synthetic results presented as banking accuracy, or an older configuration presented as the current one | M / H | every artifact is synthetic; H-27 | README figures recomputed from artifacts (`tests/unit/test_readme_numbers.py`), pitch figures pinned to `bench-v1.json` and run in CI, configuration labelled (B-004); pitch E2E guard against bank/production claims; B-057 | agent | mitigated; B-057 open |
| R-06 | Gesture feature fails on real hands during a demo | M / M | never run on a real hand | B-030 before any claim; mouse/keyboard always available (invariant) | human | open |
| R-07 | Real data enters a system without dataset isolation | L / H | roles are global (B-011); no per-dataset visibility | import off by default + admin-only (B-010, D-11); B-019 before real use | owner | mitigated for demo |
| R-08 | Dev toolchain advisories (vitest 2 / esbuild) exploited on a developer machine | L / M | `npm audit`: 2 critical, 1 high, 3 moderate (dev only); production 0 | B-013 upgrade; B-014 CI gate | agent | open |
| R-09 | Live deployment differs from the documented record | M / M | no agent has inspected Railway | B-005 | owner | open |
| R-10 | Graph freezes or blanks on larger snapshots | L / M | layout in a worker (B-020); blank stage during relayout | B-025, B-021, B-047 | agent | partly mitigated |
| R-11 | Concurrent agent sessions collide on one branch | M / M | L-0016 duplicate B-020 | fetch before writing; FF-only pushes; one working branch named in EXECUTION_STATE | agent | mitigated |
| R-12 | No backups / retention policy | M / H for real use | H-20 | B-051 (D-5) | owner | open |
| R-13 | Single-factor local passwords | M / M | H-21 | D-6 (OIDC + MFA) before real users | owner | accepted for demo |
| R-14 | Account-level recall understated on frozen generators | L / L | H-25 (≤ 0.0013) | B-048 (owner decides) | owner | accepted |

**Not claimed anywhere:** regulatory compliance, a completed penetration test, production readiness for a bank.
