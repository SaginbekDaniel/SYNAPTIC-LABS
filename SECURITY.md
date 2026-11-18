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
| HTTP Basic access control on every route except `/healthz`; container refuses to start without credentials | `apps/web/docker/10-nexora-gateway.envsh` |
| Shared gateway token required by every `/api` route (defence in depth if the API were ever exposed) | `src/nexora/api/main.py` |
| TLS terminated by Railway; HSTS when served over HTTPS | Railway edge, gateway headers |
| Content-Security-Policy (hash-pinned inline script), `X-Frame-Options: DENY`, `nosniff`, Referrer/Permissions policies | `apps/web/docker/csp.mjs` |
| Rate limits (reads 20 r/s, writes 30/min per client), 21 MiB body limit, CSV row limit | gateway config, `NEXORA_MAX_*` |
| API docs disabled in the deployment; error envelopes without stack traces | `NEXORA_EXPOSE_API_DOCS=false`, API error handlers |
| Non-root containers; secrets only in Railway variables, set over stdin | Dockerfiles, `scripts/railway/bootstrap.sh` |
| CodeQL, Dependabot (dependency review can be added once the repository's Dependency graph is enabled) | `.github/` |

What is **not** in place — and why this must not hold real data:

* **Shared demo identity.** Everyone who passes the gateway acts as `NEXORA_DEMO_ANALYST`; audit
  records cannot distinguish people. There is no SSO, no per-user accounts, no RBAC.
* Basic access control is a single shared credential, not an identity provider (Cloudflare Access,
  OIDC) with MFA, revocation and per-user audit.
* No penetration test, threat-model review, data-retention policy, encryption-key management,
  backup-restore drill, or compliance assessment has been performed.
