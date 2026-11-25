import { createHash, randomBytes } from "node:crypto";
import { defineConfig, devices } from "@playwright/test";

const API_PORT = 8100;
const WEB_PORT = 5180;
const DB = process.env.NEXORA_E2E_DATABASE_URL ?? "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_e2e";

process.env.NEXORA_E2E_TRANSFER_TOKEN ??= randomBytes(32).toString("hex");
process.env.NEXORA_E2E_SANDBOX_CUSTOMER ??= randomBytes(32).toString("hex");
process.env.NEXORA_E2E_SANDBOX_REVIEWER ??= randomBytes(32).toString("hex");
const digest = (token: string) => createHash("sha256").update(token).digest("hex");
const identities = {
  [digest(process.env.NEXORA_E2E_SANDBOX_CUSTOMER)]: {
    subject: "e2e-customer", tenant: "e2e", role: "customer", customer_ref: "demo-sender",
  },
  [digest(process.env.NEXORA_E2E_SANDBOX_REVIEWER)]: {
    subject: "e2e-reviewer", tenant: "e2e", role: "reviewer",
  },
};

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "off", locale: "ru-RU" },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testIgnore: /mobile\.spec\.ts/ },
    { name: "mobile", use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }, testMatch: /mobile\.spec\.ts/ },
  ],
  webServer: [
    {
      command: `../../scripts/e2e_stack.sh ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/health/ready`,
      env: {
        NEXORA_DATABASE_URL: DB,
        NEXORA_CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        NEXORA_TRANSFER_ANALYST_TOKEN: process.env.NEXORA_E2E_TRANSFER_TOKEN,
        NEXORA_TRANSFER_PROTECTION_ENABLED: "true",
        NEXORA_LOCAL_IDENTITY_PROVISIONING: JSON.stringify(identities),
      },
      reuseExistingServer: false,
      timeout: 60_000,
    },
    {
      command: `npx vite --port ${WEB_PORT} --strictPort`,
      url: `http://127.0.0.1:${WEB_PORT}`,
      env: { NEXORA_API_URL: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
