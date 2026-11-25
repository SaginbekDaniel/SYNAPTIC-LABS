# Execution state

The live snapshot. **Update this file at the end of every task** (and append to
[`EXECUTION_LEDGER.md`](EXECUTION_LEDGER.md)). Facts were last checked on 2026-11-25 (L-0020); stale facts must be
re-verified, not trusted. Context: [`MASTER_HANDOFF.md`](MASTER_HANDOFF.md), queue:
[`EXECUTION_BACKLOG.md`](EXECUTION_BACKLOG.md), dependencies: [`DEPENDENCY_MAP.md`](DEPENDENCY_MAP.md), risks:
[`RISK_REGISTER.md`](RISK_REGISTER.md), tests: [`TEST_MATRIX.md`](TEST_MATRIX.md), release: [`RELEASE_CHECKLIST.md`](RELEASE_CHECKLIST.md).

## Repository position

Re-checked 2026-11-25 (L-0020). Before writing: `git fetch`, compare with `origin/graph-workspace-wip`, and check that no
other session is working on this branch (two sessions collided once, L-0016) — fast-forward only, never force-push.

| Item | Value |
|---|---|
| Working branch | **`graph-workspace-wip`** — fast-forwarded `0c8d21b` → `bd3868f` in L-0020, so it again equals `claude/peaceful-darwin-nrquu9` plus this session's commits. `peaceful-darwin` is no longer written to. |
| Base | `bd3868f` (B-011 + handoff, CI runs 80–82 success) |
| Default branch | `claude/brave-dirac-c80nwq` at `ea5ca9c` (no `main`); the working branch is 54 commits ahead of it at `bd3868f`, 0 behind |
| Open PRs | #15, #5, #3 (superseded in effect by the working branch — owner decides, B-002) and Dependabot #6–#14, #16 |
| Unmerged branches without PRs | `feat/transfer-protection` (collaborator, H-26, B-056); `admiring-fermat-9fc4nx` and `great-lovelace-0gmpmi` merged into the working line by B-004 (L-0021); `eloquent-planck-pwnbd8` / `sharp-cannon-xkrybs` (content ported by B-003), `peaceful-babbage-cyqrox` (superseded) |
| Migration head | `0005` (production reportedly `0003`; `0005` makes existing accounts analysts) |
| Handoff checks | `python3 docs/handoff/probes/check_handoff_docs.py` → OK · `python3 docs/handoff/probes/progress.py` → exit 0 |

## Computed progress (`python3 docs/handoff/probes/progress.py --markdown`, 2026-11-25, after L-0025)

| Measure | Value |
|---|---|
| Verified completion (weighted) | 45.1 % |
| Critical-path progress (weighted) | 61.2 % |
| Tasks: total / done / remaining | 42 / 14 / 28 |
| Done by priority (P0, P1, P2, P3) | P0 4/6, P1 10/16, P2 0/17, P3 0/3 |
| Blocked | B-002, B-005, B-019, B-030, B-048, B-051, B-054, B-055, B-056 |
| In progress / implemented / verified | B-042 |
| Critical path still open | B-002, B-005, B-030, B-052, B-055 |
| Open P0 tasks (release-blocking) | B-002, B-030 |

Both open P0 tasks are human-gated (owner merge approval; a person with a webcam). Regenerate this table after every status change.

## Baseline verification (2026-11-25, fresh container, L-0020)

ruff / format / mypy clean · pytest **296 passed, 0 skipped** on `bd3868f` (304 with this session's progress-probe tests) ·
`alembic upgrade head` + `alembic check` clean, single head `0005` · OpenAPI client in sync · `tsc -b` clean · vitest **135** ·
`vite build` ok · Playwright **37 passed** (cold cache, 2.2 min) · `.railway` check ok · pitch: lint, tsc, **17** unit, build,
**29 E2E** passed · `npm audit --omit=dev` **0**; dev toolchain 6 (2 critical, 1 high, 3 moderate) on `bd3868f` → **0 after B-013** (L-0024).
**Not executed locally**: Docker build/compose (no daemon; CI runs it), ShellCheck and `pip-audit` (CI runs them), real webcam, live
Railway state. Playwright against the production bundle with the generated CSP: 38 passed (L-0024).

## Tasks

* **Completed backlog tasks** (status lines carry commit + ledger): B-001, B-003, B-004, B-010, B-011, B-012, B-013, B-014, B-015, B-020, B-031, B-040, B-041, B-050.
  Defect fixed outside the backlog: H-28 (`db19947`, L-0023).
  L-0020 (outside the backlog): branch consolidation, computed progress, dependency map, risk register, test matrix, release checklist,
  H-26 / B-056 / D-12.
* **Active**: B-042 — verified locally (L-0025); DONE once CI is green on its commit. Next recommended: B-022 and B-025 (graph stage), B-016, B-021, B-045.
* **Ready (autonomous)**: B-016, B-017, B-018, B-021, B-022, B-025, B-032, B-043, B-044, B-045, B-046, B-047,
  B-053. Recommended order: B-022, B-025, B-016, B-021, B-045 (adversarial dev suite before tuning anything on
  sealed-v2 findings). Every autonomous critical-path task is done; the rest of the critical path (B-002, B-005, B-030, B-052, B-055) is owner- or hardware-gated.
* **Pending (waiting on dependencies)**: B-023 (B-022), B-024 (B-021), B-033 (B-030), B-052 (B-002), B-057 (B-055).
* **Blocked (human or decision)**: B-002 (merge approval, D-1/D-2), B-005 (Railway access), B-019 (D-3), B-030 (webcam), B-048 (owner),
  B-051 (B-005, D-5), B-054 (D-10, B-047), B-055 (deployment approval), B-056 (D-12).
* **Evaluation state**: `sealed-v1` consumed; `sealed-v2` pre-registered run done (L-0015), 0 of 3 later candidate uses spent. Never tune on either.

## Explicit blockers and environment constraints

* No Docker daemon, no ShellCheck, no `pip-audit` in the build container; the sandbox refused `uvx` (do not work around it — use CI, B-014).
* PostgreSQL does not survive container restarts: `service postgresql start`, then create the `nexora` role and the `nexora`, `nexora_test`,
  `nexora_e2e` databases if missing (`docs/development/local-setup.md`; in a root container run `psql`/`createdb` via `su postgres -c`).
* The connected Railway token authenticates but lists no projects at account level; do not enumerate the owner's account to look for them.
* Owner decisions open: D-1 … D-12 (MASTER_HANDOFF §20). B-019, B-051, B-054, B-056 need answers first.

## Next exact commands

```bash
git fetch origin --prune && git checkout graph-workspace-wip && git status -sb   # fast-forward only
service postgresql start && pg_lsclusters      # fresh container: create role + 3 databases (docs/development/local-setup.md)
export UV_SYSTEM_CERTS=1 && unset UV_NATIVE_TLS && uv sync --frozen && (cd apps/web && npm ci)
python3 docs/handoff/probes/check_handoff_docs.py && python3 docs/handoff/probes/progress.py   # expect OK and exit 0
uv run pytest -p no:cacheprovider -rs                         # expect 338 passed, 0 skipped (L-0025)
(cd apps/web && npx tsc -b && npx vitest run)                 # expect 135 passed; Playwright 39
```

## Open these files first

`CLAUDE.md` · `docs/handoff/MASTER_HANDOFF.md` (§1, §6, §16, §18, §20, §23) · `docs/handoff/EXECUTION_BACKLOG.md` (B-004, B-014, B-050, B-056) ·
`docs/handoff/DEPENDENCY_MAP.md` · `docs/handoff/RELEASE_CHECKLIST.md` · `docs/handoff/probes/README.md`.

## Known risks right now

See [`RISK_REGISTER.md`](RISK_REGISTER.md). Top three: R-01 (integration line still not on the default branch; a collaborator already forked
from the stale base), R-02 (that collaborator feature carries a second auth mechanism, H-26), R-05 (headline figures describe the deployed v2, not this branch's v3, until B-057; now labelled).
Every figure in this repository is synthetic-data behaviour, not banking accuracy.
