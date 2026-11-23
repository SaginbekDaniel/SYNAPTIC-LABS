# Execution state

The live snapshot. **Update this file at the end of every task** (and append to
[`EXECUTION_LEDGER.md`](EXECUTION_LEDGER.md)). Facts were last checked on 2026-11-23 (L-0017); stale facts must be
re-verified, not trusted. Context: [`MASTER_HANDOFF.md`](MASTER_HANDOFF.md), queue:
[`EXECUTION_BACKLOG.md`](EXECUTION_BACKLOG.md).

## Repository position

Re-checked 2026-11-23 (L-0017). Before writing: `git fetch`, compare with `origin/claude/peaceful-darwin-nrquu9`, and check
that no other session is working on this branch (two sessions collided here, L-0016) — never force-push.

| Item | Value |
|---|---|
| Working branch | `claude/peaceful-darwin-nrquu9` (the only line with B-001…B-041 work; `graph-workspace-wip` stays at `0c8d21b`) |
| Last verified pushed commit before L-0017 | `3528265` — CI run 79 success |
| L-0017 commit | the commit that adds `tests/unit/test_handoff_docs_checker.py` — `git log -1 --format=%H -- tests/unit/test_handoff_docs_checker.py`; its CI run is in the ledger/final report |
| Default branch | `claude/brave-dirac-c80nwq` at `ea5ca9c` (no `main`) |
| Open PRs | #15, #5, #3 (superseded in effect by the integration line — owner decides, B-002) and Dependabot PRs |
| Unmerged branches without PRs | `eloquent-planck-pwnbd8`, `sharp-cannon-xkrybs`, `admiring-fermat-9fc4nx`, `great-lovelace-0gmpmi`, `peaceful-babbage-cyqrox` (see MASTER_HANDOFF §6) |
| Migration head | `0005` since B-011 (production reportedly `0003`; `0005` makes existing accounts analysts) |
| Handoff checker | `python3 docs/handoff/probes/check_handoff_docs.py` → OK at L-0017 (machine-independent since L-0017) |

## Baseline verification (2026-11-22, this container)

All green and re-run by hand; full table with commands in MASTER_HANDOFF §2: ruff / format / mypy clean · pytest **190 passed, 0
skipped** · `alembic upgrade head` + `alembic check` clean (head `0004`) · OpenAPI client in sync · `tsc -b` clean · vitest **99 passed** ·
`vite build` ok · Playwright **34 passed** (cold cache) · Playwright against the production bundle with the gateway headers **34 passed** ·
`.railway` check ok · pitch: lint, 17 unit, build, smoke, **29 E2E** passed · `npm audit`: 8 advisories (2 critical, 1 high, 5 moderate;
production-relevant: `react-router`).
**Not executed**: Docker build/compose (no daemon), local ShellCheck, `pip-audit`, real webcam, live Railway state, camera path through the
real Nginx image, ORM load/publish at 200k rows.

## Tasks

* **Completed backlog tasks**: B-001 (L-0005), B-010 (L-0006), B-003 (L-0007), B-015 (L-0008), B-012 (L-0009), B-031 (L-0010),
  B-020 (L-0011), B-041 (L-0013), B-040 (L-0015), B-011 (L-0018). Outside the backlog: handoff-checker fixes and finding H-25 (L-0017).
* **Active**: none. Next recommended: B-004 (README/pitch numbers vs verified artifacts).
* **Ready (dependencies met, autonomous)**: B-004, B-019 (needs decision D-3 first), B-013, B-014, B-016, B-017, B-018, B-021, B-022, B-025, B-032, B-042,
  B-043, B-044, B-045, B-046, B-047, B-048 (owner decides first), B-050, B-053. Recommended order: B-004, B-016,
  B-021, B-013, B-014, B-022, B-025, B-042, B-045 (adversarial dev suite before tuning anything on sealed-v2 findings).
* **Pending (waiting on dependencies)**: B-023 (B-022), B-024 (B-021), B-033 (B-030),
  B-052 (B-002, B-004), B-054 (B-047).
* **Human-gated**: B-002 (approve merges/closures), B-005 (live Railway access), B-030 (a person with a webcam), B-051 (live
  backups, owner decisions D-5), B-055 (deployment approval).
* **Evaluation state**: `sealed-v1` consumed; `sealed-v2` pre-registered run done (L-0015), 0 of 3 later candidate uses
  spent. Never tune on either.

## Explicit blockers and environment constraints

* No Docker daemon, no ShellCheck, no `pip-audit` in the build container; the sandbox refused `uvx` (do not work around it — use CI, B-014).
* PostgreSQL does not stay running between container starts: `service postgresql start`, then check the `nexora` role and the
  `nexora`, `nexora_test`, `nexora_e2e` databases exist (`docs/development/local-setup.md`).
* The connected Railway token authenticates but lists no projects at account level; do not enumerate the owner's account to look for them.
* Owner decisions open: D-1 … D-11 (D-11: import needs admin — assumed by B-011) (MASTER_HANDOFF §20). Defaults assumed where stated in the backlog; B-019, B-051, B-054 need answers first.

## Next exact commands

```bash
git fetch origin --prune && git checkout claude/peaceful-darwin-nrquu9 && git status -sb   # fast-forward only
service postgresql start && pg_lsclusters      # fresh container: create role + 3 databases (docs/development/local-setup.md)
export UV_SYSTEM_CERTS=1 && unset UV_NATIVE_TLS && uv sync --frozen && (cd apps/web && npm ci)
python3 docs/handoff/probes/check_handoff_docs.py            # expect OK
uv run pytest -p no:cacheprovider -rs                         # expect 296 passed, 0 skipped (L-0018)
(cd apps/web && npx tsc -b && npx vitest run)                 # expect 135 passed; Playwright 37 (L-0018)
```

## Open these files first

`CLAUDE.md` · `docs/handoff/MASTER_HANDOFF.md` (§1, §6, §16, §18, §23) · `docs/handoff/EXECUTION_BACKLOG.md` (B-011, B-019, B-025) ·
`migrations/versions/` · `src/nexora/api/deps.py` · `src/nexora/auth/service.py` · `src/nexora/api/routes/` · `tests/integration/test_auth.py` ·
`docs/handoff/probes/README.md`.

## Known risks right now

1. Two open PRs define migration `0003`; never renumber the auth migration (production reportedly at `0003`). 2. ~~The CSV import route is open to
any signed-in user~~ — closed by default (B-010 done). 3. ~~Published benchmark arithmetic off by ≤ 0.1 pp~~ — fixed and artifacts regenerated under A2 (B-003 done); the pitch still carries old numbers (B-004). 4. `sealed-v1` is
consumed — do not tune against it; `sealed-v2` pre-registered run done (B-040), 0 of 3 later uses spent. 5. Camera recognition has never run on a real hand (B-030); the camera now starts only after the model has loaded (B-031). 6. ~~Graph layout freezes the UI~~ — layout runs in a worker (B-020 done); the stage still blanks during relayout (B-025). 9. Account-level recall on frozen generators counts a few never-transacting truth accounts (H-25, B-048). 7. Live deployment state is unverified (B-005). 8. Every figure above is synthetic-data behaviour, not banking accuracy.
