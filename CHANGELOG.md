# Changelog

All notable changes to this project. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
No versions have been released yet; entries are grouped by merged pull request.

## [Unreleased]

### Added
- **Authentication**: named analyst accounts (Argon2id), server-side sessions in PostgreSQL
  (opaque 256-bit tokens, only SHA-256 digests stored; idle and absolute expiry; revocation on
  sign-out, password change and account disable), `HttpOnly` `Secure` `SameSite=Strict` `__Host-`
  cookie, session-bound CSRF token, trusted-origin checks, per-name and per-client brute-force
  throttling plus a gateway rate limit on sign-in. Every `/api` route requires a session by default
  (`/api/v1/auth/login` and `/api/v1/auth/session` are the only public ones). Migration `0003`.
- `POST /api/v1/auth/login`, `GET /api/v1/auth/session`, `GET /api/v1/auth/me`, `POST /api/v1/auth/logout`.
- Operator CLI `python -m nexora.auth.cli` (create-user, set-password, disable/enable,
  revoke-sessions, list-users, hash-password, bootstrap); one-time provisioning from
  `NEXORA_BOOTSTRAP_USERNAME` + `NEXORA_BOOTSTRAP_PASSWORD_HASH` at API start-up.
- NEXORA sign-in page (brand panel with an animated, decorative network; accessible form with
  password visibility, Caps Lock hint, loading and throttling states), route guard with return to
  the requested page, session-expiry re-authentication, sign-out in the rail and the phone sheet.
- Gateway `session` mode (default): no browser Basic prompt; requires the gateway token.
- Deployed to Railway (`nexora-ai-demo`): PostgreSQL, API, worker and gateway; see the deployment record in `docs/deployment/railway.md`.
- Railway deployment: Infrastructure-as-Code definition (`.railway/railway.ts`) with an offline
  invariant check, bootstrap and ordered deploy scripts, and a manual, approval-gated GitHub
  Actions deployment that refuses commits without a green CI run.
- Gateway hardening: fail-closed HTTP Basic access control, gateway→API shared token, hash-pinned
  Content-Security-Policy, security headers, rate limits, runtime DNS re-resolution of the API.
- `NEXORA_EXPOSE_API_DOCS`, `NEXORA_GATEWAY_TOKEN`, `NEXORA_DB_POOL_SIZE`, `NEXORA_DB_MAX_OVERFLOW`.
- Hosted PostgreSQL URLs (`postgres://`, `postgresql://`) are accepted and mapped to psycopg 3.
- Worker stops cooperatively on SIGTERM after finishing the job in progress.
- Deployed smoke test (`apps/web/playwright.smoke.config.ts`) and a CI job that builds the
  production images and runs it through the gateway with access control on.
- CodeQL, Dependabot, issue/PR templates, `SECURITY.md`, `CONTRIBUTING.md`,
  Makefile, deployment and architecture documentation.

### Changed
- Audit events and analysis jobs record the signed-in analyst; `NEXORA_DEMO_ANALYST` and the
  `actor` field of `/health/ready` are removed.
- The gateway no longer proxies `/health/*` (readiness is for the platform's private probe).
- Python image is multi-stage (no build tooling at runtime); gateway runs as unprivileged Nginx.

### Fixed
- `migrations/env.py` no longer disables loggers created before an in-process migration.
- Generating a dataset in the Fraud Lab no longer snaps the active dataset back to the previous
  one when other datasets exist (the "go to alerts" link showed the old dataset's queue).

## PR #2 — NEXORA Dark Intelligence redesign (merged)
- Redesigned analyst UI, server-side alert queue paging/search/sort with facet counts, overview
  activity chart, large-graph readability, design documentation.

## PR #1 — Investigation UI, detectors v2, benchmark (merged)
- Investigation UI, E2E tests, Docker Compose, CI; detectors v2 with peer statistics and
  `risk-policy-v2`; reproducible synthetic benchmark `bench-v1` and research documentation.
