import { defineConfig, devices } from "@playwright/test";

/**
 * Smoke test against an already-running NEXORA gateway (local Docker stack or a cloud deployment).
 * It starts nothing and resets nothing: it only adds synthetic datasets and one case decision.
 *
 *   NEXORA_SMOKE_URL        base URL, e.g. https://<service>.up.railway.app  (default http://127.0.0.1:8080)
 *   NEXORA_SMOKE_USER       gateway user      } omit both when the gateway runs with
 *   NEXORA_SMOKE_PASSWORD   gateway password  } NEXORA_GATEWAY_AUTH=off (local stack)
 *   NEXORA_SMOKE_SCREENSHOTS  directory to write README screenshots to (optional)
 */
const user = process.env.NEXORA_SMOKE_USER;
const password = process.env.NEXORA_SMOKE_PASSWORD;

export default defineConfig({
  testDir: "smoke",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 120_000,
  reporter: [["list"]],
  use: {
    baseURL: process.env.NEXORA_SMOKE_URL ?? "http://127.0.0.1:8080",
    httpCredentials: user && password ? { username: user, password } : undefined,
    trace: "off",
    locale: "ru-RU",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testIgnore: /mobile/ },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }, testMatch: /mobile/ },
  ],
});
