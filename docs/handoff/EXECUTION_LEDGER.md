# Execution ledger

Append-only. One entry per task attempt or session, newest last. Never edit a past entry — add a new one that
corrects it. Record commands and their **literal** results; mark anything not run as "not executed".

Entry template:

```
### L-NNNN · YYYY-MM-DD · B-0xx (or "session") · status: done | partial | blocked | abandoned
* Branch / commits: `branch` · `<sha>` …
* Changes: …
* Verification (commands → observed): …
* Not executed / limitations: …
* Findings or follow-ups (new H-nn / B-nn): …
* State file updated: yes/no
```

---

### L-0001 · 2026-11-21 · session (gesture/graph verification) · status: done
* Branch / commits: `graph-workspace-wip` · `7abd9a5` (on top of checkpoint `b9943f0`).
* Changes: reproduced and fixed four defects — MediaPipe not pre-bundled in Vite (full-page reload mid-session; the gesture E2E failed on every cold
  cache), worker network guard deleted `WebSocket` (now guards fetch/XHR/WebSocket/EventSource), MediaPipe's `INFO:` stderr logged as an error
  (`workerConsole.ts`), Cytoscape rejecting CSS Color 4 tokens (`canvasColor.ts`); added the real-webcam checklist (not executed) and the first
  `ZENCODER_*` handoff documents.
* Verification: ruff/format/mypy clean; pytest 190 passed; alembic head `0004` + check clean; vitest 99; vite build; Playwright 34 (cold cache) and
  34 against the production bundle with gateway headers; `.railway` check; pitch 17 unit + 29 E2E. GitHub CI run 64 → success `[CI]`.
* Not executed: Docker build locally, local ShellCheck, pip-audit, real webcam.
* State file updated: n/a (state file did not exist).

### L-0002 · 2026-11-22 · session (master handoff and audit) · status: done
* Branch / commits: `claude/peaceful-darwin-nrquu9` · base `7abd9a5` · handoff commit = `git log -1 --format=%H -- docs/handoff/MASTER_HANDOFF.md`.
* Changes: **documentation and probes only — no product code changed.** Added `MASTER_HANDOFF.md`, `EXECUTION_BACKLOG.md` (38 tasks, 6 waves),
  `NEXT_SESSION_PROMPT.md`, `EXECUTION_STATE.md`, this ledger, `probes/` (three measurement scripts + a gateway stand-in); added a "superseded"
  banner to the three earlier `ZENCODER_*` documents.
* Verification (all re-run by hand, literal results in MASTER_HANDOFF §2): ruff / format / mypy clean; pytest 190 passed (0 skipped); alembic head
  `0004`, no drift; OpenAPI no diff; tsc clean; vitest 99; vite build; Playwright 34 (cold cache); Playwright against the production bundle 34;
  `.railway` check; pitch lint + 17 unit + build + smoke + 29 E2E; `npm audit` 8 advisories. GitHub CI run 64 read through the API → success.
  Probes: pipeline 200k transfers 22.5 s / 381 MiB; graph read model hub 20k peers 215–640 ms; `cose` layout 200 nodes 1,150 ms, 300 nodes 2,791 ms.
* Not executed: Docker image build/compose (no daemon), local ShellCheck, `pip-audit`, real webcam, live Railway state, camera path through the
  real Nginx image, ORM load/publish at 200k rows.
* Findings: H-01 … H-24 registered in MASTER_HANDOFF §16 (new this session: H-01 migration collision, H-02 open CSV import, H-03 invalid JSON logs,
  H-04 layout freeze, H-05 camera-before-model, H-06 N+1/over-fetch, H-08 benchmark arithmetic, H-10…H-22 design risks, H-23, H-24); four unmerged
  branches discovered (eloquent-planck, great-lovelace, admiring-fermat, sharp-cannon) plus the stale peaceful-babbage.
* State file updated: yes (created).
