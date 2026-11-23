import { expect, test, type BrowserContext, type Page } from "@playwright/test";
import { syntheticHand } from "../src/features/gestures/syntheticHands";
import { collectErrors, seedAndAnalyse } from "./helpers";

/**
 * Camera gestures. CI has no webcam: Chromium's fake device supplies real MediaStream frames, and
 * the scripted-journey test swaps only the landmark *worker script* for one that replays synthetic
 * hands. Real-hardware recognition is verified manually (docs/implementation/GRAPH_GESTURE_VERIFICATION.md).
 */

/** Every request any page or worker makes; the camera mode must never reach another origin. */
function foreignRequests(context: BrowserContext, origin: string): string[] {
  const foreign: string[] = [];
  context.on("request", (r) => {
    const u = new URL(r.url());
    if (u.protocol.startsWith("http") && u.origin !== origin) foreign.push(r.url());
  });
  return foreign;
}

/** Count getUserMedia calls and keep the returned streams so the test can check they were stopped. */
async function instrumentCamera(page: Page, deny = false) {
  await page.addInitScript((denyAccess) => {
    const w = window as unknown as { __gum: number; __streams: MediaStream[] };
    w.__gum = 0;
    w.__streams = [];
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (c) => {
      w.__gum++;
      if (denyAccess) throw new DOMException("denied by the test", "NotAllowedError");
      const s = await original(c);
      w.__streams.push(s);
      return s;
    };
  }, deny);
}
const gumCalls = (page: Page) => page.evaluate(() => (window as unknown as { __gum: number }).__gum);
const liveTracks = (page: Page) =>
  page.evaluate(() => (window as unknown as { __streams: MediaStream[] }).__streams.flatMap((s) => s.getTracks()).filter((t) => t.readyState === "live").length);

async function openGraph(page: Page, seed: string) {
  await seedAndAnalyse(page, seed);
  await page.goto("/network");
  // The force layout runs in a worker; the graph can be driven once the canvas reports "ready".
  await expect(page.getByTestId("graph-canvas")).toHaveAttribute("data-layout", "ready", { timeout: 30_000 });
}

test("consent comes before the browser prompt, and denial leaves the graph fully usable", async ({ page, context, baseURL }) => {
  const errors = collectErrors(page);
  const foreign = foreignRequests(context, new URL(baseURL!).origin);
  await instrumentCamera(page, true);
  await openGraph(page, "5201");

  await page.getByTestId("gesture-toggle").click();
  await expect(page.getByTestId("gesture-consent")).toContainText("только в этом браузере");
  expect(await gumCalls(page)).toBe(0); // explanation first, no camera request yet
  await page.getByRole("button", { name: "Отмена" }).click();
  await expect(page.getByTestId("gesture-consent")).toHaveCount(0);
  expect(await gumCalls(page)).toBe(0);

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  await expect(page.getByTestId("gesture-status")).toContainText("Доступ к камере запрещён");
  await expect(page.getByTestId("gesture-toggle")).toHaveAttribute("aria-pressed", "false");

  // Mouse/keyboard path still works.
  await page.getByTestId("graph-canvas").focus();
  await page.keyboard.press("]");
  await page.keyboard.press("Enter");
  await expect(page.locator("#account-summary")).toBeVisible();
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]);
});

test("real recogniser on a synthetic camera: self-hosted model, no foreign traffic, clean stop", async ({ page, context, baseURL }) => {
  test.setTimeout(120_000);
  const errors = collectErrors(page);
  const origin = new URL(baseURL!).origin;
  const foreign = foreignRequests(context, origin);
  const vendor: string[] = [];
  context.on("requestfinished", (r) => {
    if (r.url().includes("/vendor/mediapipe/")) vendor.push(new URL(r.url()).pathname);
  });
  await instrumentCamera(page);
  await openGraph(page, "5202");

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  // The model loaded and frames are flowing; the synthetic camera shows no hand.
  await expect(page.getByTestId("gesture-status")).toContainText("Покажите руку в кадре", { timeout: 60_000 });
  await expect(page.getByTestId("gesture-panel")).toContainText("Камера включена");
  expect(await liveTracks(page)).toBe(1);
  expect(vendor.sort()).toEqual(expect.arrayContaining(["/vendor/mediapipe/hand_landmarker.task", "/vendor/mediapipe/vision_wasm_module_internal.wasm"]));

  await page.getByTestId("gesture-stop").click();
  await expect(page.getByTestId("gesture-toggle")).toHaveAttribute("aria-pressed", "false");
  expect(await liveTracks(page)).toBe(0);
  // MediaPipe flushes its usage metrics when it is closed; the worker's guard keeps them local.
  await page.waitForTimeout(2500);
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]);
});

test("the camera stays off until the recognition model has loaded (H-05)", async ({ page, context }) => {
  test.setTimeout(120_000);
  const errors = collectErrors(page);
  // Hold every model/WASM download until the test has looked at the loading state.
  let release!: () => void;
  const gate = new Promise<void>((r) => (release = r));
  const held: string[] = [];
  await context.route("**/vendor/mediapipe/**", async (route) => {
    held.push(new URL(route.request().url()).pathname);
    await gate;
    await route.continue();
  });
  await instrumentCamera(page);
  await openGraph(page, "5204");

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  const status = page.getByTestId("gesture-status");
  await expect(status).toContainText("Загрузка модели распознавания");
  await expect.poll(() => held.length, { timeout: 30_000 }).toBeGreaterThan(0); // the worker is really waiting on assets
  await page.waitForTimeout(1000); // give a premature camera request every chance to happen
  await expect(status).toContainText("Загрузка модели распознавания");
  expect(await gumCalls(page)).toBe(0);
  expect(await liveTracks(page)).toBe(0);
  // The panel does not claim a live camera, and the control cancels rather than "turns off the camera".
  await expect(page.getByTestId("gesture-panel")).not.toContainText("Камера включена");
  await expect(page.getByTestId("gesture-stop")).toHaveText("Отменить включение");

  release();
  await expect(status).toContainText("Покажите руку в кадре", { timeout: 60_000 });
  expect(await gumCalls(page)).toBe(1);
  expect(await liveTracks(page)).toBe(1);
  await expect(page.getByTestId("gesture-panel")).toContainText("Камера включена");
  await expect(page.getByTestId("gesture-stop")).toHaveText("Выключить камеру");
  await page.getByTestId("gesture-stop").click();
  expect(await liveTracks(page)).toBe(0);
  expect(errors).toEqual([]);
});

test("leaving the page or hiding the tab releases the camera", async ({ page }) => {
  await instrumentCamera(page);
  await openGraph(page, "5203");
  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  await expect.poll(() => liveTracks(page), { timeout: 30_000 }).toBe(1);
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "hidden", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  await expect(page.getByTestId("gesture-status")).toContainText("пока вкладка была скрыта");
  expect(await liveTracks(page)).toBe(0);
  await page.evaluate(() => {
    Object.defineProperty(document, "visibilityState", { value: "visible", configurable: true });
    document.dispatchEvent(new Event("visibilitychange"));
  });
  expect(await liveTracks(page)).toBe(0); // coming back never restarts the camera by itself

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  await expect.poll(() => liveTracks(page), { timeout: 30_000 }).toBe(1);
  await page.getByRole("link", { name: "Проверки" }).first().click();
  await expect(page).toHaveURL(/\/alerts/);
  await expect.poll(() => liveTracks(page)).toBe(0);
});

/** A landmark worker that replays a scripted hand journey (same synthetic hands as the unit tests). */
function scriptedWorker(): string {
  // Anchor offsets of the synthetic hand (scale 0.15): placing the hand here puts the pointer at the
  // camera centre, which the selfie mapping turns into the centre of the graph stage.
  return `
const syntheticHand = ${syntheticHand.toString()};
let t0 = null;
const point = () => [syntheticHand("point", { x: 0.5375, y: 0.62 })];
const pinch = () => [syntheticHand("pinch", { x: 0.56375, y: 0.5675 })];
self.onmessage = (e) => {
  const m = e.data;
  if (m.type === "init") return self.postMessage({ type: "ready" });
  if (m.type === "close") return self.close();
  m.bitmap.close();
  if (t0 === null) t0 = m.t;
  const dt = m.t - t0;
  let hands = [];
  if (dt >= 400 && dt < 1400) hands = point();
  else if (dt >= 1400 && dt < 1800) hands = pinch();
  else if (dt >= 1800 && dt < 2200) hands = point();
  else if (dt >= 2200 && dt < 3400) hands = [syntheticHand("open", { x: 0.62 - 0.2 * ((dt - 2200) / 1200), y: 0.5 })];
  self.postMessage({ type: "result", t: m.t, hands });
};`;
}

test("scripted hand journey: calibrate, point, pinch-select, palm-pan, lose the hand", async ({ page, context, baseURL }) => {
  test.setTimeout(90_000);
  const errors = collectErrors(page);
  const foreign = foreignRequests(context, new URL(baseURL!).origin);
  await instrumentCamera(page);
  await page.route(/landmarkWorker[^/]*\.(ts|js)/, (route) => route.fulfill({ contentType: "text/javascript", body: scriptedWorker() }));
  await openGraph(page, "5204");

  // Put the top-priority account in the centre of the stage, where the scripted pinch happens.
  await page.getByTestId("graph-canvas").focus();
  await page.keyboard.press("]");
  const announced = page.locator(".graph-stage [aria-live=polite]").first();
  await expect(announced).toContainText("Счёт ");
  const id = (await announced.innerText()).replace(/^Счёт /, "").split(",")[0]!.trim();
  await page.waitForTimeout(400); // centring animation

  await page.getByTestId("gesture-toggle").click();
  await page.getByTestId("gesture-start").click();
  const status = page.getByTestId("gesture-status");
  await expect(status).toContainText("Рука в кадре", { timeout: 15_000 });
  await expect(page.getByTestId("gesture-pointer")).toBeVisible();
  // Pinch on the centred account selects it (navigation mode never moves it).
  await expect(page.locator("#account-summary")).toContainText(id, { timeout: 15_000 });
  await expect(status).toContainText("сдвиг", { timeout: 15_000 });
  await expect(status).toContainText("Рука не видна — жест отменён", { timeout: 15_000 });
  await expect(page.getByTestId("gesture-pointer")).toHaveCount(0);

  await page.keyboard.press("Escape");
  await expect(page.getByTestId("gesture-toggle")).toHaveAttribute("aria-pressed", "false");
  expect(await liveTracks(page)).toBe(0);
  expect(foreign).toEqual([]);
  expect(errors).toEqual([]);
});
