/**
 * NEXORA AI — Railway project definition (Infrastructure as Code).
 *
 *   Internet ──HTTPS──▶ web (Nginx gateway, the ONLY public service)
 *                         │  private network, X-Nexora-Gateway-Token
 *                         ▼
 *                       api (FastAPI) ── pre-deploy: alembic upgrade head
 *                         │
 *   worker (jobs) ──────▶ postgres (Railway PostgreSQL, persistent volume)
 *
 * Apply with the Railway CLI (`railway config plan`, then `railway config apply`); see
 * docs/deployment/railway.md. Code is uploaded per service with `railway up` by
 * scripts/railway/deploy.sh, so this file declares no repository source.
 *
 * Secrets are never written here. They are set once with `railway variable set KEY --stdin`
 * (scripts/railway/bootstrap.sh) and kept by preserve():
 *   api  NEXORA_GATEWAY_TOKEN              gateway ↔ API secret; web references the api's value
 *   web  NEXORA_GATEWAY_USER / _PASSWORD   demo access credentials
 */
import { defineRailway, group, postgres, preserve, project, service } from "railway/iac";

const MiB = 1024 * 1024;

export default defineRailway(() => {
  const db = postgres("postgres");

  // Settings shared by the two Python roles (same image, different start command).
  const appEnv = {
    // Railway's private PostgreSQL URL (postgresql://…); NEXORA rewrites it to the psycopg 3 driver.
    NEXORA_DATABASE_URL: db.env.DATABASE_URL,
    NEXORA_DEMO_ANALYST: "demo-analyst",
    // Two pools (api + worker) × (3 + 2) stays far below PostgreSQL's 100 connections.
    NEXORA_DB_POOL_SIZE: "3",
    NEXORA_DB_MAX_OVERFLOW: "2",
    NEXORA_WORKER_POLL_SECONDS: "2",
  };

  const api = service("api", {
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    env: {
      ...appEnv,
      NEXORA_GATEWAY_TOKEN: preserve(),
      PORT: "8000",
      // IPv4. Verified on the first deploy: with "::" Railway's health probe never reached uvicorn (no
      // request in the access log) and the deploy failed. This environment resolves private names to
      // IPv4 as well as IPv6, so 0.0.0.0 serves both the probe and the gateway.
      NEXORA_BIND_HOST: "0.0.0.0",
      // Same-origin behind the gateway: no cross-origin callers, no public API documentation.
      NEXORA_CORS_ORIGINS: "",
      NEXORA_EXPOSE_API_DOCS: "false",
    },
    deploy: {
      // Runs once per deploy, before the new API starts serving; the worker never migrates.
      preDeployCommand: ["alembic upgrade head"],
      preDeployTimeoutSeconds: 300,
      healthcheckPath: "/health/ready",
      healthcheckTimeout: 120,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      drainingSeconds: 25,
      limitOverride: { containers: { cpu: 1, memoryBytes: 512 * MiB } },
    },
  });

  const worker = service("worker", {
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    env: appEnv,
    deploy: {
      startCommand: "python -m nexora.worker.runner",
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 10,
      // SIGTERM → the worker finishes the job in progress; a killed job is re-leased anyway.
      drainingSeconds: 60,
      limitOverride: { containers: { cpu: 1, memoryBytes: 1024 * MiB } },
    },
  });

  const web = service("web", {
    build: { builder: "DOCKERFILE", dockerfilePath: "Dockerfile" },
    env: {
      PORT: "8080",
      NEXORA_API_UPSTREAM: { value: "${{api.RAILWAY_PRIVATE_DOMAIN}}:8000" },
      NEXORA_GATEWAY_TOKEN: api.env.NEXORA_GATEWAY_TOKEN,
      NEXORA_GATEWAY_AUTH: "basic",
      NEXORA_GATEWAY_USER: preserve(),
      NEXORA_GATEWAY_PASSWORD: preserve(),
    },
    deploy: {
      healthcheckPath: "/healthz",
      healthcheckTimeout: 60,
      restartPolicyType: "ON_FAILURE",
      restartPolicyMaxRetries: 5,
      limitOverride: { containers: { cpu: 0.5, memoryBytes: 256 * MiB } },
    },
  });

  return project("nexora-ai-demo", {
    resources: [group("NEXORA", [web, api, worker, db])],
  });
});
