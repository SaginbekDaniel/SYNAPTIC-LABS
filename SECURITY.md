# Security policy

NEXORA AI is a **hackathon prototype on synthetic data**. It is not connected to any bank, holds no
real customer data, and is **not** hardened, tested or reviewed to the standard of a banking system.

## Reporting a vulnerability

Please report privately through GitHub: **Security → Report a vulnerability** on this repository
(private vulnerability reporting). If that option is not available, open an issue titled
"Security contact request" **without technical details**, and a maintainer will arrange a private
channel. Please do not publish details before a fix or a decision has been agreed.

Include the affected commit, the steps to reproduce, and the impact you observed. Only test against
your own local stack (`docker compose up`) or with the maintainers' permission — never against
infrastructure you do not own.

## Supported versions

Only the default branch is maintained. There are no releases yet.

## Security model of the demo deployment

What is in place (see [docs/deployment/railway.md](docs/deployment/railway.md#security-model)):

| Control | Where |
|---|---|
| Single public entry point; API, worker and PostgreSQL only on the private network | Railway topology (`.railway/railway.ts`) |
| **Named analyst accounts**; passwords hashed with Argon2id (RFC 9106 low-memory profile), ≥ 12 characters, NFKC-normalised; no default or published accounts | `src/nexora/auth/passwords.py`, operator CLI `python -m nexora.auth.cli` |
| **Server-side sessions** in PostgreSQL: 256-bit random opaque token in an `HttpOnly`, `Secure`, `SameSite=Strict`, `__Host-` cookie; only its SHA-256 is stored; idle (2 h) and absolute (12 h) expiry; revoked on sign-out, password change, account disable or by an operator | `src/nexora/auth/service.py`, `src/nexora/api/routes/auth.py` |
| **Every `/api` route requires a session by default**; only `POST /auth/login` and the read-only `GET /auth/session` are public (enforced by a global dependency and by a test that enumerates every route) | `src/nexora/api/deps.py`, `tests/integration/test_auth.py` |
| CSRF: session-bound synchronizer token (HMAC of the session secret) required on every write; trusted-origin check (`Origin` / `Sec-Fetch-Site`); sign-in only accepts JSON (forces a CORS preflight) | `src/nexora/api/deps.py`, `src/nexora/auth/tokens.py` |
| Session fixation: a new token on every sign-in; any session the browser presented is revoked | `auth.service.sign_in` |
| Brute force: 5 failures per user name and 30 per client per 15 min (counted for unknown names too, so lockout does not reveal accounts) → `429` with `Retry-After`; gateway limit 10 sign-ins/min per address; Argon2 work bounded to 2 concurrent hashes | `auth.service`, gateway config |
| No account enumeration: unknown user, wrong password and disabled account return the same `401` after the same Argon2 work | `auth.service.sign_in` |
| Audit: sign-in, sign-out and account changes are audit events; case actions and analysis jobs record the session's user, never a client-supplied name | `audit_events`, `case_service`, `analysis_service` |
| No secrets in logs, URLs or browser storage: submitted user names are stored only as a keyed digest; the password is a `SecretStr`; the CSRF token lives in memory only | tests in `test_auth.py`, `e2e/auth.spec.ts` |
| Shared gateway token required by every `/api` route (defence in depth: the API only accepts requests that came through the gateway) | `src/nexora/api/main.py` |
| Gateway fails closed: refuses to start without a ≥ 32-character gateway token (`session` mode) or without Basic credentials (`basic` mode) | `apps/web/docker/10-nexora-gateway.envsh` |
| TLS terminated by Railway; HSTS when served over HTTPS | Railway edge, gateway headers |
| Content-Security-Policy (hash-pinned inline script), `X-Frame-Options: DENY`, `nosniff`, Referrer/Permissions policies; `Cache-Control: no-store` on every API response | `apps/web/docker/csp.mjs`, API middleware |
| **CSV upload disabled by default** (`POST /api/v1/datasets/import` → `403 CSV_IMPORT_DISABLED`, refused after authentication but before the upload is read); pinned off in the deployment definition and checked by its invariant test; only the synthetic Fraud Lab creates data | `NEXORA_ALLOW_CSV_IMPORT`, `src/nexora/api/routes/datasets.py`, `.railway/check.ts` |
| Rate limits (reads 20 r/s, writes 30/min, sign-in 10/min per client), 21 MiB body limit, CSV row limit | gateway config, `NEXORA_MAX_*` |
| API docs and readiness details not served publicly; error envelopes without stack traces | `NEXORA_EXPOSE_API_DOCS=false`, gateway, API error handlers |
| Non-root containers; secrets only in Railway variables, set over stdin | Dockerfiles, `scripts/railway/bootstrap.sh` |
| CodeQL, Dependabot | `.github/` |

What is **not** in place — and why this must not hold real data:

* **No SSO or MFA; global roles only.** Accounts are local passwords managed by an operator CLI. Each
  account has a role — `viewer` (reads only), `analyst` (generates synthetic data, runs analyses, works
  cases; the default) or `admin` (also CSV import when enabled) — enforced on the server per route and
  changed only through the operator CLI. Every account still sees every dataset: there is no per-dataset
  isolation (backlog B-019, decision D-3). There is no self-service password reset. An identity provider
  (OIDC) with MFA is the right next step for anything beyond a demo (see ADR 020).
* Sign-in throttling counts in the database and is approximate under concurrent bursts; the gateway
  rate limit bounds it. There is no CAPTCHA or anomaly detection.
* No penetration test, threat-model review, data-retention policy, encryption-key management,
  backup-restore drill, or compliance assessment has been performed.
