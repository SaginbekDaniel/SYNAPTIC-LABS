# Release checklist

Gates a release must pass **in order**. A 100 % figure from `docs/handoff/probes/progress.py` does not replace any gate.
Tick a box only with the evidence named next to it (command output, CI run URL, dated record). State at 2026-11-25 (L-0020).

## 1. Integration

- [ ] One integrated line: the default branch contains the integration line (B-002, decision D-1) — *open: default branch at `ea5ca9c`*
- [ ] Collaborator work integrated or explicitly deferred (B-056, D-12) — *open*
- [ ] No open P0 task (`progress.py`: "Open P0 tasks") — *open: B-002, B-030*
- [x] Single Alembic head; migrations additive since production's `0003` (B-001) — `uv run alembic heads` → `0005 (head)`

## 2. Quality gates (cold cache, observed output)

- [x] ruff, ruff format, mypy clean — L-0020
- [x] pytest 0 failed, **0 skipped** — L-0020
- [x] tsc, vitest, vite build — L-0020
- [x] OpenAPI client in sync — L-0020
- [x] Playwright full suite from a cold `node_modules/.vite` — L-0020 (37 passed)
- [ ] Playwright against the production bundle with the gateway CSP headers — *last run L-0011 (B-020); re-run on the release commit*
- [ ] CI green on the release commit (all three jobs) — *record the run URL*
- [x] Dependency audit gate on production dependencies with negative controls (B-014; audit run 1: npm 0, Python 0)
- [ ] Dev toolchain advisories closed (B-013)

## 3. Security

- [x] Public surface = `POST /auth/login` + `GET /auth/session`; every other route authenticated, CSRF on writes, role declared (B-011)
- [x] CSV import off by default and admin-only when on (B-010, D-11)
- [ ] Threat model reviewed for any new surface (B-056 if integrated)
- [ ] No secret in Git history of the release diff (`git diff <base>..<release> | grep -iE 'password|secret|token|key'`, reviewed by eye)

## 4. Product claims

- [x] README and pitch numbers trace to committed artifacts (B-004; `tests/unit/test_readme_numbers.py`, `apps/pitch/src/data/bench.test.ts`)
- [ ] Gesture control: verified on a real webcam (B-030) **or** stated as an unverified limitation in README, pitch and demo script
- [ ] Every metric labelled synthetic; no bank-accuracy, compliance or production-readiness claim

## 5. Deployment (owner approval required — B-055)

- [ ] Owner approval recorded (date, commit)
- [ ] Live state inspected first (B-005): current deployment SHA, migration revision, env vars present (names only)
- [ ] Migration plan confirmed: `0003 → head` applies only `0004`, `0005` (additive); `0005` makes existing accounts `analyst`
- [ ] `NEXORA_ALLOW_CSV_IMPORT=false` in production
- [ ] Deploy via the approval-gated workflow `.github/workflows/deploy-railway.yml`
- [ ] Deployed smoke test (`apps/web/playwright.smoke.config.ts`) passes against the public URL
- [ ] `/health/ready` reports the expected revision
- [ ] Rollback rehearsed or documented for this release (redeploy previous deployment; migrations additive)
- [ ] Dated deployment record in `docs/deployment/railway.md`

## 6. Handoff

- [ ] EXECUTION_STATE, ledger, backlog statuses and DEPENDENCY_MAP regenerated; `check_handoff_docs.py` OK
- [ ] Known limitations listed in `docs/LIMITATIONS.md` match the release
- [ ] Working tree clean; release commit pushed
