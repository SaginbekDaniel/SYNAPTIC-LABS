# Next session prompt

Paste everything below the line as the first message of a new autonomous coding session on this repository.

---

You are the lead engineer for **NEXORA AI / SYNAPTIC-LABS** (explainable fraud/AML triage for a human analyst; synthetic data only).
Your job in this session is to **implement, verify and push real changes** from the prepared backlog — not to write another plan.
Work autonomously through as many tasks as you can finish properly; stop only at the conditions in §8.

## 1. Recover the repository state first (no assumptions)

```bash
git fetch origin --prune
git checkout graph-workspace-wip                # the working line since L-0020 (= peaceful-darwin + later work); see EXECUTION_STATE.md if it names a newer branch
git status -sb && git log --oneline -5 && git branch -r | grep -v dependabot && git worktree list && git stash list
```

If your harness assigned you a different working branch, create it from this one and use it for pushes. Then list the open PRs
(GitHub MCP `list_pull_requests`, state open) and compare with `docs/handoff/EXECUTION_STATE.md`. If anything differs from that file,
the repository wins — record the difference in the ledger.

## 2. Read, in this order

1. `CLAUDE.md` (binding rules). 2. `docs/handoff/MASTER_HANDOFF.md` — at least §1, §6 (branch/PR hazard), §12 (benchmark rules), §16
(findings), §18 (invariants), §23 (Definition of Done). 3. `docs/handoff/EXECUTION_STATE.md`. 4. `docs/handoff/EXECUTION_BACKLOG.md`
(the task you will start and its prerequisites). 5. `docs/handoff/probes/README.md`. Skim `docs/ADR/0001-decisions.md` and
`docs/architecture/DEEP_AUDIT.md` when a task touches detection. Treat every number in the handoff as historical until you reproduce it.

## 3. Establish your own verified baseline

```bash
service postgresql start; pg_lsclusters          # it does not survive container restarts; the role/databases are listed in docs/development/local-setup.md
export UV_SYSTEM_CERTS=1; unset UV_NATIVE_TLS
uv sync --frozen && (cd apps/web && npm ci)
uv run ruff check src tests migrations && uv run ruff format --check src tests migrations && uv run mypy
uv run pytest -p no:cacheprovider -rs            # expected: 304 passed, 0 skipped (L-0020)
NEXORA_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora uv run alembic upgrade head
NEXORA_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora uv run alembic check
cd apps/web && npx tsc -b && npx vitest run      # expected: 135 passed
npx vite build && npm run gen:api && git -C "$(git rev-parse --show-toplevel)" diff --exit-code -- apps/web/openapi.json apps/web/src/lib/api-types.ts
npx playwright install chromium && rm -rf node_modules/.vite && npx playwright test --trace off   # expected: 37 passed
cd ../../.railway && npm ci && npm run check
```

Write the literal outcomes into the ledger. If a number differs from the expectation, **stop and investigate before starting any task**.
Known environment limits: no Docker daemon, no ShellCheck, no `pip-audit`; if a tool is refused by the sandbox, do not work around it
(use CI or tell the owner). Never claim a check passed that you did not run.

## 4. Select work

Take the first task that is (a) not human-gated, (b) has all its dependencies done (each task's `Status` and `Depends on` lines in the
backlog; `python3 docs/handoff/probes/progress.py` lists what is blocked), and (c) is highest in the "Recommended order" of
`EXECUTION_STATE.md`, then by priority (P0, P1, P2). Human-gated / decision-gated tasks (B-002, B-005, B-019, B-030, B-048, B-051, B-054,
B-055, B-056): do **not** start them yourself; ask the owner once (see §8), then carry on with other work. Set the task's `Status` to
`IN_PROGRESS` and mark it `Active` in `EXECUTION_STATE.md` before you begin; set `DONE · commit `<sha>` · L-nnnn` only after CI is green,
then regenerate the dependency map (`progress.py --mermaid`) and the progress table (`progress.py --markdown`).

## 5. Per-task loop (do all of it)

1. `git checkout -b feat/b-0xx-<slug>` from the current working branch.
2. **Reproduce first**: write the failing test or measurement that demonstrates the problem (the backlog names it). Show it failing.
3. Implement the root-cause fix, following the repository's patterns. Prefer the existing abstractions; no unrelated refactors; do not
   optimise for the smallest diff — optimise for correctness → maintainability → UX → regression safety.
4. Run **focused tests**, then the **full gate** (§3 commands; Playwright from a cold `node_modules/.vite`). For web work also look at the
   real UI in a browser (both themes, 1440 px and 390 px) and check the console is clean.
5. **Security review** of your own diff: authentication/authorization impact, CSRF/origin, input validation, secrets/logging, new endpoints
   (public surface must stay `login` + `session`), the camera invariants, dependency/licence impact.
6. Update docs that changed (never invent a number: metrics only from executed runs), regenerate generated files
   (`npm run gen:api` after API changes), remove obsolete code.
7. `git add` only intended files; scan the staged diff for secrets (`git diff --cached | grep -iE 'password|secret|token|key'` and look);
   commit with a message that states what, why, and the verification; end the message with the attribution lines your harness specifies.
8. Push to your feature branch (`git push -u origin <branch>`; retry network errors up to 4 times with backoff). **No force-push, no history
   rewrite of shared branches, no merge into the default branch, no deployment, no `git push` to a branch you do not own.**
9. Update `EXECUTION_STATE.md` (Completed/Active/Pending/blockers/next commands) and append an entry to `EXECUTION_LEDGER.md` (commands →
   literal results, what was not executed, new findings).
10. Immediately continue with the next eligible task.

## 6. Task-specific warnings

* **Migrations** — `0001`–`0004` are immutable; production is reportedly at `0003` = the auth migration. New migrations take the next free
  revision, are additive, and you must keep a single Alembic head. Do not renumber or "fix" `0003`/`0004`.
* **B-003 (benchmark arithmetic)** — port the commits from `origin/claude/eloquent-planck-pwnbd8` and `origin/claude/sharp-cannon-xkrybs` by cherry-pick;
  resolve the four conflicts keeping the integration branch's structure; **regenerate** `bench-v1.json`, `dev-evaluation.json`,
  `sealed-evaluation.json` with the scripts, never by hand; prove every detection count is unchanged; record protocol amendment A2.
* **Evaluation** — `sealed-v1` is consumed: do not tune against it. Lock a protocol commit **before** running any candidate on a new split. Report
  distinct-network P@K. Everything is synthetic; say so.
* **Gestures** — keep `optimizeDeps.include: ["@mediapipe/tasks-vision"]`, the worker's same-origin guard, the consent-first flow, camera release on
  every exit path. Do not describe real-device behaviour as verified; only B-030 can do that.
* **Graph** — `GraphController` has no write commands; graph views show stored assessments only; colours given to Cytoscape go through `toCanvasColor()`.
* **UI** — copy only through `apps/web/src/lib/i18n.ts`, styling only through `apps/web/src/styles/tokens.css`; mobile/PWA behaviour, safe areas and keyboard
  handling are first-class; never fix a layout problem with arbitrary offsets without finding the cause.
* **Tests** — never weaken, skip or delete a test to get green; if behaviour changed deliberately, say why in the commit.

## 7. Evidence discipline

Report only what you ran. For every claim give the command and the observed result. If something was not executed, say "not executed" and why.
Distinguish confirmed defects from hypotheses. Do not present synthetic benchmark numbers as banking performance.

## 8. Stop conditions — and what to ask the owner

Stop and report when: all eligible autonomous tasks are done; a baseline check fails and you cannot fix its root cause; a task needs a decision in
`MASTER_HANDOFF.md §20`; or a task needs something only a human can do. Ask the owner (once, concisely, then continue elsewhere) for:
**B-002** approval to merge/close PRs #3/#5/#15 and to dispose of stale branches; **B-005** workspace/project access to read the live Railway state;
**B-030** a person with a webcam to run `docs/implementation/GRAPH_GESTURE_VERIFICATION.md`; **B-055** explicit approval before any deployment;
and answers to D-3 (data isolation model), D-4 (CSV import default), D-5 (retention), D-6 (MFA/identity provider), D-10 (real-time requirement) when you reach
the tasks that depend on them.

## 9. Final report format

End the session (or each long stretch) with: branch and commit SHA(s) pushed; each gate command with its literal result and which checks you could not
run; tasks completed with files changed and the tests that prove them; tasks started but unfinished; newly found defects (with reproduction); blockers and
questions for the owner; and "what would still feel broken or inconsistent if this shipped tomorrow".
