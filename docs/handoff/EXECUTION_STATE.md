# Execution state

The live snapshot. **Update this file at the end of every task** (and append to
[`EXECUTION_LEDGER.md`](EXECUTION_LEDGER.md)). Everything here was checked on 2026-11-22; stale facts must be
re-verified, not trusted. Context: [`MASTER_HANDOFF.md`](MASTER_HANDOFF.md), queue:
[`EXECUTION_BACKLOG.md`](EXECUTION_BACKLOG.md).

## Repository position

| Item | Value |
|---|---|
| Working branch (this handoff) | `claude/peaceful-darwin-nrquu9` |
| Verified code base | `7abd9a549629338c710d69403fbce2c019bee285` (`graph-workspace-wip`, identical content) |
| Handoff commit | the commit after the base that adds `docs/handoff/*` — `git log -1 --format=%H -- docs/handoff/MASTER_HANDOFF.md` |
| `graph-workspace-wip` on GitHub | still at `7abd9a5` (the handoff commit was pushed only to the working branch); to align without force: `git push origin claude/peaceful-darwin-nrquu9:graph-workspace-wip` (fast-forward) |
| Default branch | `claude/brave-dirac-c80nwq` at `ea5ca9c` (no `main`); integration line is 25 commits ahead, 0 behind |
| Open PRs | #15, #5, #3 (superseded in effect by the integration line — owner decides, B-002) and Dependabot #6–#14 |
| Unmerged branches without PRs | `eloquent-planck-pwnbd8`, `sharp-cannon-xkrybs`, `admiring-fermat-9fc4nx`, `great-lovelace-0gmpmi`, `peaceful-babbage-cyqrox` (see MASTER_HANDOFF §6) |
| GitHub CI | run 64 on `7abd9a5` → success; run 65 on `da681c2` → one intermittent auth E2E test failed (test race, fixed — ledger L-0003); the fix commit's run is recorded in the final report / ledger |

## Baseline verification (2026-11-22, this container)

All green and re-run by hand; full table with commands in MASTER_HANDOFF §2: ruff / format / mypy clean · pytest **190 passed, 0
skipped** · `alembic upgrade head` + `alembic check` clean (head `0004`) · OpenAPI client in sync · `tsc -b` clean · vitest **99 passed** ·
`vite build` ok · Playwright **34 passed** (cold cache) · Playwright against the production bundle with the gateway headers **34 passed** ·
`.railway` check ok · pitch: lint, 17 unit, build, smoke, **29 E2E** passed · `npm audit`: 8 advisories (2 critical, 1 high, 5 moderate;
production-relevant: `react-router`).
**Not executed**: Docker build/compose (no daemon), local ShellCheck, `pip-audit`, real webcam, live Railway state, camera path through the
real Nginx image, ORM load/publish at 200k rows.

## Tasks

* **Completed backlog tasks**: none yet. (Earlier, outside the backlog: the four fixes and the verification checklist in commit
  `7abd9a5` — MediaPipe pre-bundling, worker network guard for all four channels, `INFO:` stderr routing, `toCanvasColor`.)
* **Active**: none.
* **Ready now (autonomous, no human input, dependencies met)**: B-001, B-003, B-010, B-012, B-013, B-015, B-017, B-020, B-022, B-031, B-040,
  B-041, B-047, B-050, B-053. Recommended order: **B-001 → B-010 → B-003 → B-015 → B-012 → B-031 → B-020 → B-040/B-041**.
* **Pending (waiting on dependencies)**: B-004, B-011, B-014, B-016, B-018*, B-019, B-021, B-023, B-024, B-032, B-033, B-042..B-046, B-052, B-054
  (*B-018 has no dependency and may start any time).
* **Human-gated**: B-002 (approve merges/closures), B-005 (live Railway access), B-030 (a person with a webcam), B-051 (live backups, owner
  decisions D-5), B-055 (deployment approval).

## Explicit blockers and environment constraints

* No Docker daemon, no ShellCheck, no `pip-audit` in the build container; the sandbox refused `uvx` (do not work around it — use CI, B-014).
* PostgreSQL does not stay running between container starts: `service postgresql start`, then check the `nexora` role and the
  `nexora`, `nexora_test`, `nexora_e2e` databases exist (`docs/development/local-setup.md`).
* The connected Railway token authenticates but lists no projects at account level; do not enumerate the owner's account to look for them.
* Owner decisions open: D-1 … D-10 (MASTER_HANDOFF §20). Defaults assumed where stated in the backlog; B-019, B-051, B-054 need answers first.

## Next exact commands

```bash
git fetch origin --prune && git checkout claude/peaceful-darwin-nrquu9 && git status -sb
service postgresql start && pg_lsclusters
export UV_SYSTEM_CERTS=1 && unset UV_NATIVE_TLS && uv sync --frozen && (cd apps/web && npm ci)
uv run pytest -p no:cacheprovider -rs                       # expect 190 passed, 0 skipped
(cd apps/web && npx tsc -b && npx vitest run)               # expect 99 passed
git checkout -b feat/b-001-migration-chain-guard             # then start B-001 (see EXECUTION_BACKLOG.md)
```

## Open these files first

`CLAUDE.md` · `docs/handoff/MASTER_HANDOFF.md` (§1, §6, §16, §18, §23) · `docs/handoff/EXECUTION_BACKLOG.md` (B-001, B-010, B-003) ·
`migrations/versions/` · `src/nexora/api/routes/datasets.py` · `src/nexora/evaluation/benchmark.py` · `apps/web/src/features/gestures/gestureSession.ts` ·
`docs/handoff/probes/README.md`.

## Known risks right now

1. Two open PRs define migration `0003`; never renumber the auth migration (production reportedly at `0003`). 2. The CSV import route is open to
any signed-in user (B-010). 3. Published benchmark arithmetic is off by ≤ 0.1 pp and the fix is on an unmerged branch (B-003). 4. `sealed-v1` is
consumed — do not tune against it (B-040). 5. Camera recognition has never run on a real hand (B-030). 6. Graph layout freezes the UI for 1–3 s at
200–300 nodes (B-020). 7. Live deployment state is unverified (B-005). 8. Every figure above is synthetic-data behaviour, not banking accuracy.
