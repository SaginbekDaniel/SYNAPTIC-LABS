import { defineConfig, devices } from "@playwright/test";
import { AUTH_STATE, E2E_PASSWORD } from "./e2e/helpers";

const API_PORT = 8100;
const WEB_PORT = 5180;
const DB = process.env.NEXORA_E2E_DATABASE_URL ?? "postgresql+psycopg://nexora:nexora@localhost:5432/nexora_e2e";

export default defineConfig({
  testDir: "e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [["list"]],
  use: { baseURL: `http://127.0.0.1:${WEB_PORT}`, trace: "off", locale: "ru-RU" },
  projects: [
    // Signs in once through the real form; the journeys below reuse that session.
    { name: "setup", testMatch: /auth\.setup\.ts/ },
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, storageState: AUTH_STATE },
      dependencies: ["setup"],
      testIgnore: /(mobile|auth|gestures)\.spec\.ts/,
    },
    {
      name: "mobile",
      use: { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, storageState: AUTH_STATE },
      dependencies: ["setup"],
      testMatch: /mobile\.spec\.ts/,
    },
    // Sign-in, session and sign-out flows start without a session.
    { name: "auth", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } }, testMatch: /auth\.spec\.ts/ },
    {
      // Camera gestures: Chromium's synthetic camera stands in for hardware (no webcam in CI).
      name: "gestures",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 900 },
        storageState: AUTH_STATE,
        permissions: ["camera"],
        launchOptions: { args: ["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"] },
      },
      dependencies: ["setup"],
      testMatch: /gestures\.spec\.ts/,
    },
  ],
  webServer: [
    {
      command: `../../scripts/e2e_stack.sh ${API_PORT}`,
      url: `http://127.0.0.1:${API_PORT}/health/ready`,
      env: {
        NEXORA_DATABASE_URL: DB,
        NEXORA_CORS_ORIGINS: `http://127.0.0.1:${WEB_PORT}`,
        NEXORA_E2E_PASSWORD: E2E_PASSWORD,
        // Plain-HTTP dev server: Secure cookies would not round-trip. Production keeps the default (true).
        NEXORA_SESSION_COOKIE_SECURE: "false",
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
