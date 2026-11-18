# Changelog

All notable changes to this project. Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
No versions have been released yet; entries are grouped by merged pull request.

## [Unreleased]

### Added
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
- Python image is multi-stage (no build tooling at runtime); gateway runs as unprivileged Nginx.

### Fixed
- Generating a dataset in the Fraud Lab no longer snaps the active dataset back to the previous
  one when other datasets exist (the "go to alerts" link showed the old dataset's queue).

## PR #2 — NEXORA Dark Intelligence redesign (merged)
- Redesigned analyst UI, server-side alert queue paging/search/sort with facet counts, overview
  activity chart, large-graph readability, design documentation.

## PR #1 — Investigation UI, detectors v2, benchmark (merged)
- Investigation UI, E2E tests, Docker Compose, CI; detectors v2 with peer statistics and
  `risk-policy-v2`; reproducible synthetic benchmark `bench-v1` and research documentation.
