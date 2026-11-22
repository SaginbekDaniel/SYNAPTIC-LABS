# Zencoder execution prompt

> **SUPERSEDED by [`NEXT_SESSION_PROMPT.md`](NEXT_SESSION_PROMPT.md) (kept for history).** The new prompt adds branch recovery, an execution queue,
> a per-task loop, an execution ledger and the corrected migration/PR guidance (MASTER_HANDOFF H-01).

> **Transfer status:** no Zencoder integration (CLI, MCP server, plugin or connector) was available
> in the environment that prepared this handoff, so nothing was transferred automatically. To start,
> open the repository in Zencoder and paste everything below the line as the first message.

---

You are continuing development of **NEXORA AI**, an explainable financial-network investigation
prototype (synthetic data only). You are taking over a verified checkpoint of the **Graph
Workspace** and opt-in **camera Gesture Control** features. Work as a senior engineer who owns the
product: find root causes, prefer maintainable fixes, preserve working behaviour, and report only
results you actually observed.

## 1. Get the code

```bash
git clone https://github.com/SaginbekDaniel/SYNAPTIC-LABS.git
cd SYNAPTIC-LABS
git fetch origin graph-workspace-wip
git checkout -b zencoder/graph-workspace-next origin/graph-workspace-wip
```

The default branch is `claude/brave-dirac-c80nwq` (there is no `main`). `graph-workspace-wip`
locally merges three PRs that are still open on GitHub (#15, #3, #5) — see the handoff §6.

## 2. Read before changing anything

1. `CLAUDE.md` — binding project rules (integer money, opaque ids, pure `nexora.domain`/`analytics`,
   UI copy only via `apps/web/src/lib/i18n.ts`, styling only via `styles/tokens.css`, regenerate the
   OpenAPI client after API changes, the commit gates).
2. `docs/handoff/ZENCODER_HANDOFF.md` — architecture, what is done, what is not, verified results.
3. `docs/handoff/ZENCODER_TASKS.md` — prioritised tasks T1–T11 with requirements and test criteria.
4. `docs/implementation/GRAPH_GESTURE_VERIFICATION.md` — manual webcam checklist (not yet run).

Then inspect the code yourself — do not take the documents on trust. Key files:
`apps/web/src/features/graph/GraphWorkspace.tsx`, `apps/web/src/components/graph/{GraphCanvas,controller,canvasColor}.ts(x)`,
`apps/web/src/features/gestures/*`, `apps/web/vite.config.ts`, `apps/web/scripts/gesture-assets.mjs`,
`apps/web/docker/{csp.mjs,default.conf.template}`, `src/nexora/application/graph_view.py`,
`src/nexora/api/routes/analysis.py`, `tests/integration/test_investigation_graph.py`,
`apps/web/e2e/{graph-workspace,gestures}.spec.ts`.

## 3. Establish your own baseline

Requires Python 3.12/3.13 + uv, Node 22, PostgreSQL 16 (role `nexora`/`nexora`, databases
`nexora`, `nexora_test`, `nexora_e2e` — see `docs/development/local-setup.md`).

```bash
uv sync --frozen
uv run ruff check src tests migrations && uv run ruff format --check src tests migrations
uv run mypy
uv run pytest                                   # expect 190 passed, 0 skipped
NEXORA_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora uv run alembic upgrade head
NEXORA_DATABASE_URL=postgresql+psycopg://nexora:nexora@localhost:5432/nexora uv run alembic check
cd apps/web && npm ci
npx tsc -b && npx vitest run                    # expect 99 passed
npx vite build                                  # downloads + hash-verifies the hand model once
npm run gen:api && git -C "$(git rev-parse --show-toplevel)" diff --exit-code -- apps/web/openapi.json apps/web/src/lib/api-types.ts
npx playwright install chromium
rm -rf node_modules/.vite && npx playwright test --trace off   # expect 34 passed
```

If your numbers differ, stop and investigate before starting new work; report the difference.

## 4. What to do

Work through `ZENCODER_TASKS.md` in this order unless the owner says otherwise:
T3 (production image + gateway smoke) → T2 (real webcam; needs a human with a camera) →
T4 + T5 (documentation) → T1 (PR stack — owner decides) → T6 → T7 → T8–T10.
**T11 (deployment) only with explicit owner approval.**

For each task: implement → add or update tests that would have caught the problem → run the full
gate → inspect the actual UI in a browser (both themes, 1440 px and 390 px) → check for regressions
→ remove obsolete code → commit.

## 5. Invariants you must preserve

* Camera is off by default; the consent dialog precedes the browser prompt; the camera is released
  on stop, Esc, hidden tab, route change, unmount, camera loss and engine failure.
* The browser makes **no cross-origin request**: keep the worker's same-origin guard
  (`sameOriginGuard.ts`, all four channels) and the CSP `connect-src 'self'`. E2E asserts this.
* MediaPipe assets stay self-hosted and SHA-256-pinned; production builds fail closed.
* Keep `optimizeDeps.include: ["@mediapipe/tasks-vision"]` in `vite.config.ts` (removing it brings
  back a full page reload mid-session in dev and fails the gesture E2E on a cold cache).
* Colours passed to Cytoscape go through `toCanvasColor()`.
* `GraphController` has no write commands; gestures can never change cases or data.
* The graph shows stored assessments only; the graph endpoint never scores.
* Never modify or delete a test to hide a regression; never fabricate results.

## 6. Git rules

* Commit verified work to your feature branch (e.g. `zencoder/graph-workspace-next`) and push it.
* No force-push, no history rewrite of shared branches, no merge into the default branch, no
  deployment — without explicit approval from the repository owner.
* No secrets in Git (`.env*` is ignored; use `.env.example` for names only).
* After any API schema change run `cd apps/web && npm run gen:api` and commit both generated files.

## 7. Report back

End each working session with:
1. Branch name and commit SHA(s) pushed.
2. Each gate command and its literal result (pass counts, failures) — and which checks you could
   not run and why.
3. Tasks completed, with the files changed and the tests that prove them.
4. Unresolved blockers, open questions for the owner, and anything that would still feel broken or
   inconsistent if this shipped tomorrow.
