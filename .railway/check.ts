/**
 * Offline check of railway.ts (no Railway account needed): evaluates the definition with the
 * SDK and asserts the deployment invariants NEXORA's security model depends on.
 * Full evaluation against live state is `railway config plan` (see docs/deployment/railway.md).
 */
import { createRailwayContext, type ServiceNode } from "railway/iac";
import program from "./railway.ts";

const failures: string[] = [];
const check = (ok: boolean, message: string) => {
  if (!ok) failures.push(message);
};

const ctx = createRailwayContext({ command: "plan", environment: "production", environmentName: "production" });
const definition = await program(ctx, (name, def) => ({ name, ...def }));
const nodes = (definition.resources ?? []).flat();
const services = new Map(
  nodes.filter((n): n is ServiceNode => n.type === "service").map((n) => [n.name, n] as const),
);

check(nodes.some((n) => n.type === "database"), "a PostgreSQL database is declared");
for (const name of ["api", "worker", "web"]) check(services.has(name), `service "${name}" is declared`);

const env = (name: string) => services.get(name)?.variables ?? {};
const literal = (name: string, key: string) => {
  const v = env(name)[key];
  return v && v.type === "literal" ? v.value : undefined;
};

// Secrets are references or preserved values, never committed literals.
const SECRET = /(PASSWORD|TOKEN|SECRET|DATABASE_URL)$/;
for (const [name, svc] of services) {
  for (const [key, value] of Object.entries(svc.variables ?? {})) {
    if (SECRET.test(key)) check(value.type !== "literal", `${name}.${key} must not be a literal value`);
  }
}

// Only the API migrates, before it serves; the worker and gateway never do.
check(
  JSON.stringify(services.get("api")?.deploy?.preDeployCommand) === JSON.stringify(["alembic upgrade head"]),
  "api runs `alembic upgrade head` as its pre-deploy command",
);
for (const name of ["worker", "web"]) check(!services.get(name)?.deploy?.preDeployCommand, `${name} has no pre-deploy step`);

check(literal("api", "NEXORA_EXPOSE_API_DOCS") === "false", "api does not expose /docs");
check(literal("api", "NEXORA_CORS_ORIGINS") === "", "api allows no cross-origin callers");
check(literal("web", "NEXORA_GATEWAY_AUTH") === "basic", "gateway enforces access control");
const webToken = env("web").NEXORA_GATEWAY_TOKEN;
check(
  webToken?.type === "reference" && webToken.resource === "service.api" && webToken.output === "NEXORA_GATEWAY_TOKEN",
  "gateway forwards the API's own gateway token (reference, not a copy)",
);
check(literal("api", "NEXORA_EXECUTION_PROFILE") === "deployed_demo", "deployed API validates its secrets");
check(env("api").NEXORA_TRANSFER_ANALYST_TOKEN?.type === "preserve", "analyst evidence secret is independently managed");
check(!("NEXORA_GATEWAY_TOKEN" in env("worker")), "worker does not receive the gateway token");
check(services.get("worker")?.deploy?.startCommand === "python -m nexora.worker.runner", "worker start command");
check(services.get("api")?.deploy?.healthcheckPath === "/health/ready", "api readiness health check");
check(services.get("web")?.deploy?.healthcheckPath === "/healthz", "gateway health check");
for (const [name, svc] of services) {
  check(Boolean(svc.deploy?.limitOverride?.containers?.memoryBytes), `${name} has a memory limit`);
  check(!svc.networking?.serviceDomains && !svc.networking?.customDomains, `${name}: domains are not declared here`);
}

if (failures.length) {
  console.error(`railway.ts: ${failures.length} invariant(s) violated:\n - ${failures.join("\n - ")}`);
  process.exit(1);
}
console.log(`railway.ts: ${services.size} services + database, all deployment invariants hold`);
