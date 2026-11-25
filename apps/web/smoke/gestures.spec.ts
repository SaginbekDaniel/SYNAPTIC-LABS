import { expect, request, test, type BrowserContext, type Page } from "@playwright/test";
import { collectErrors, signIn } from "../e2e/helpers";

/**
 * Camera gestures through the REAL gateway (backlog B-050). The browser E2E suite exercises gestures against the Vite
 * dev server; this spec covers what only the production path has: Nginx serving the self-hosted MediaPipe assets with
 * the generated Content-Security-Policy, and the recogniser starting under that policy. Chromium's fake camera stands
 * in for hardware (project "gestures" in playwright.smoke.config.ts); real-webcam recognition is B-030.
 *
 * The last test is a negative control: it removes 'wasm-unsafe-eval' from every response the browser receives and
 * expects the recogniser to fail. If that test ever passes without the policy, the positive test proves nothing.
 */

const smokeUser = process.env.NEXORA_SMOKE_USER ?? "";
const smokePassword = process.env.NEXORA_SMOKE_PASSWORD ?? "";
test.skip(!smokeUser || !smokePassword, "set NEXORA_SMOKE_USER and NEXORA_SMOKE_PASSWORD (an analyst account)");

const WASM = "/vendor/mediapipe/vision_wasm_module_internal.wasm";
const MODEL = "/vendor/mediapipe/hand_landmarker.task";

function foreignRequests(context: BrowserContext, origin: string): string[] {
  const foreign: string[] = [];
  context.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol.startsWith("http") && u.origin !== origin) foreign.push(r.url());
  });
  return foreign;
}

/** Count camera streams so the test can prove the camera was really on, then really off. */
async function instrumentCamera(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __streams: MediaStream[] };
    w.__streams = [];
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (c) => {
      const s = await original(c);
      w.__streams.push(s);
      return s;
    };
  });
}
const liveTracks = (page: Page) =>
  page.evaluate(() =>
    (window as unknown as { __streams: MediaStream[] }).__streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === "live").length,
  );

/** Sign in, generate a small synthetic suite and wait for the deployed worker, then open the graph workspace. */
async function openGraphWithData(page: Page) {
  const seed = String(Date.now() % 1_000_000_000);
  await page.goto("/lab");
  await signIn(page, smokeUser, smokePassword);
  await page.locator('input[name="suite"][value="demo-v1"]').check();
  await page.getByText("Параметры генерации").click();
  await page.locator('input[name="seed"]').fill(seed);
  await page.getByRole("button", { name: "Сгенерировать набор" }).click();
  await expect(page.getByTestId("import-report")).toBeVisible();
  await page.getByRole("button", { name: "Запустить анализ" }).click();
  await expect(page.getByTestId("job-status")).toContainText("готово", { timeout: 90_000 });
  await page.goto("/network");
  await expect(page.getByTestId("graph-canvas")).toHaveAttribute("data-layout", "ready", { timeout: 60_000 });
}

test("gateway serves the self-hosted model under the production policy", async ({ baseURL }) => {
  const anon = await request.newContext({ baseURL });
  const shell = await anon.get("/network");
  expect(shell.status()).toBe(200);
  const csp = shell.headers()["content-security-policy"] ?? "";
  expect(csp).toContain("'wasm-unsafe-eval'"); // WebAssembly compilation only; no 'unsafe-eval'
  expect(csp).not.toContain("'unsafe-eval'");
  expect(csp).toContain("worker-src 'self'");
  expect(csp).toContain("connect-src 'self'");
  expect(shell.headers()["permissions-policy"] ?? "").toContain("camera=(self)");

  const wasm = await anon.get(WASM);
  expect(wasm.status()).toBe(200);
  expect(wasm.headers()["content-type"]).toContain("application/wasm"); // streaming compilation requires it
  expect(wasm.headers()["content-security-policy"]).toBe(csp);
  const model = await anon.get(MODEL);
  expect(model.status()).toBe(200);
  expect(model.headers()["content-type"] ?? "").not.toContain("text/html");
  expect((await model.body()).byteLength).toBeGreaterThan(1_000_000);
  // A missing asset is a 404, never the SPA's index.html (which the loader would try to parse as a model).
  expect((await anon.get("/vendor/mediapipe/does-not-exist.task")).status()).toBe(404);
  await anon.dispose();
});

test("recogniser starts on a camera through the gateway: no policy violation, no foreign request, clean stop", async ({
  page,
  context,
  baseURL,
}) => {
  test.setTimeout(240_000);
  const errors = collectErrors(page);
  const foreign = foreignRequests(context, new URL(baseURL!).origin);
  const vendor: string[] = [];
  context.on("requestfinished", (r) => {
    if (r.url().includes("/vendor/mediapipe/")) vendor.push(new URL(r.url()).pathname);
  });
  await instrumentCamera(page);
  await openGraphWithData(page);

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  await expect(page.getByTestId("gesture-status")).toContainText("Покажите руку в кадре", { timeout: 90_000 });
  await expect(page.getByTestId("gesture-panel")).toContainText("Камера включена");
  expect(await liveTracks(page)).toBe(1);
  expect(vendor).toEqual(expect.arrayContaining([MODEL, WASM]));

  await page.getByTestId("gesture-stop").click();
  await expect(page.getByTestId("gesture-toggle")).toHaveAttribute("aria-pressed", "false");
  expect(await liveTracks(page)).toBe(0);
  await page.waitForTimeout(2500); // MediaPipe flushes usage metrics on close; they must stay on this origin
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]); // Chromium reports CSP violations, including the worker's, as console errors
});

test("negative control: without 'wasm-unsafe-eval' the recogniser cannot start", async ({ page, context }) => {
  test.setTimeout(240_000);
  const errors = collectErrors(page);
  // Same gateway, same bundle; only the policy the browser sees is weakened by one token.
  await context.route(
    (url) => !url.pathname.startsWith("/api/"),
    async (route) => {
      const response = await route.fetch();
      const headers = { ...response.headers() };
      if (headers["content-security-policy"]) {
        headers["content-security-policy"] = headers["content-security-policy"].replace("'wasm-unsafe-eval' ", "");
      }
      await route.fulfill({ response, headers });
    },
  );
  await instrumentCamera(page);
  await openGraphWithData(page);

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  await expect(page.getByTestId("gesture-status")).toContainText("Не удалось загрузить модель распознавания", { timeout: 90_000 });
  expect(await liveTracks(page)).toBe(0); // the model loads before the camera is requested (B-031)
  expect(errors.join("\n")).toMatch(/Content Security Policy|wasm-unsafe-eval|WebAssembly/i);
  // The graph stays usable with mouse and keyboard.
  await page.getByTestId("graph-canvas").focus();
  await page.keyboard.press("]");
  await page.keyboard.press("Enter");
  await expect(page.locator("#account-summary")).toBeVisible();
});
