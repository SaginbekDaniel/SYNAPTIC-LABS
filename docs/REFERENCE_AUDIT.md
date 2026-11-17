# Reference audit (Stage 0)

**Date:** 2026-11-17 · **Auditor:** Claude Code session on branch `claude/brave-dirac-c80nwq`

## Workspace baseline

| Check | Result |
|---|---|
| `git status` before work | Empty repository, branch `claude/brave-dirac-c80nwq`, no commits |
| Remote | `https://github.com/SaginbekDaniel/SYNAPTIC-LABS` |
| Existing code / tests | None — nothing to preserve or regress |
| Toolchain found | Python 3.13.18, Node 22.23.4, PostgreSQL 16 binaries, Docker 29, Chromium + Playwright 1.63 |

## Reference repositories

The master spec names six reference repositories (Vantage AI, Jigas, UNRU AI, Natural
Intelligence, Synex, Moggers under `github.com/BAITC-Hacks`).

| Repository | Inspected? | Reason |
|---|---|---|
| All six | **No** | This session's GitHub access is scoped to `SaginbekDaniel/SYNAPTIC-LABS`; the public GitHub API returned HTTP 403 through the session proxy. |

Consequences, applied as the spec's fallback rule (§2.2, §25 "If network access is unavailable"):

* **No source code, data, figures or UI assets were copied** from any reference repository.
* Their commit SHAs, licences and dataset rights were **not verified** in this session.
* NEXORA is an independent implementation written from the *behavioural requirements* in
  the master specification only. Concepts the spec attributes to the references (formation
  types, completeness/boundary reasoning, capacity-constrained flow, peer anomalies, case
  audit entities, Cytoscape graph exploration) are cited as conceptual inspiration in
  `docs/PROVENANCE.md`.
* The historical HackAlem/Freedom dataset is **not used**. All data is generated locally by
  `nexora.evaluation.generator`.

## Open items for the team

1. Inspect the six repositories at exact SHAs from a machine with access; record licences.
2. Confirm with ITU organisers whether pre-existing code is permitted and how to disclose it.
3. Until (1)–(2) are resolved, keep the zero-copy policy.
