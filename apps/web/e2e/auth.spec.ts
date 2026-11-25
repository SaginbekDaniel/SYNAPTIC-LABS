import { expect, test, type Page } from "@playwright/test";
import { collectErrors, E2E_PASSWORD, E2E_SECOND_USER, E2E_USER, E2E_VIEWER, seedAndAnalyse, signIn } from "./helpers";

// These flows start signed out (the "auth" project has no stored session).
const shots = process.env.NEXORA_E2E_SCREENSHOTS;

/** Console errors other than the HTTP status the test provoked on purpose. */
function unexpected(errors: string[], ...allowed: number[]) {
  return errors.filter((e) => !allowed.some((s) => e.includes(`status of ${s}`)));
}

async function noHorizontalOverflow(page: Page) {
  const { scroll, client } = await page.evaluate(() => ({ scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth }));
  expect(scroll).toBeLessThanOrEqual(client);
}

test("a protected route shows the NEXORA sign-in page, and the API refuses anonymous calls", async ({ page }) => {
  const errors = collectErrors(page);
  let basicPrompt = false;
  page.on("response", (r) => {
    if (r.headers()["www-authenticate"]) basicPrompt = true;
  });
  await page.goto("/alerts?band=high");
  await expect(page).toHaveURL(/\/login\?next=%2Falerts%3Fband%3Dhigh$/);
  await expect(page.getByRole("heading", { name: "С возвращением" })).toBeVisible();
  await expect(page.getByText("Intelligence Behind Every Connection")).toBeVisible();
  await expect(page.getByText("Защищённая демонстрация · только синтетические данные")).toBeVisible();
  // No fake features: no OAuth, password recovery, MFA or "remember me" controls.
  await expect(page.getByTestId("login-panel").getByRole("link")).toHaveCount(0);
  await expect(page.getByTestId("login-panel").getByRole("checkbox")).toHaveCount(0);

  const api = await page.request.get("/api/v1/datasets");
  expect(api.status()).toBe(401);
  expect((await api.json()).error.code).toBe("AUTH_REQUIRED");
  expect(basicPrompt).toBe(false);
  expect(unexpected(errors)).toEqual([]); // the anonymous page load itself produces no failing request
});

test("form validation, password visibility and keyboard-only sign-in", async ({ page }) => {
  await page.goto("/login");
  const user = page.getByTestId("login-username");
  const pass = page.getByTestId("login-password");
  await expect(user).toBeFocused(); // desktop: precise pointer

  await page.keyboard.press("Enter");
  await expect(page.getByText("Введите имя пользователя.")).toBeVisible();
  await expect(user).toHaveAttribute("aria-invalid", "true");
  await expect(user).toBeFocused();

  await page.keyboard.type(E2E_USER);
  await page.keyboard.press("Enter");
  await expect(page.getByText("Введите пароль.")).toBeVisible();
  await expect(pass).toBeFocused();

  await page.keyboard.type(E2E_PASSWORD);
  await expect(pass).toHaveAttribute("type", "password");
  await page.keyboard.press("Tab"); // → show/hide password
  const reveal = page.getByTestId("login-reveal");
  await expect(reveal).toBeFocused();
  await expect(reveal).toHaveAccessibleName("Показать пароль");
  await page.keyboard.press("Space");
  await expect(pass).toHaveAttribute("type", "text");
  await expect(reveal).toHaveAttribute("aria-pressed", "true");
  await expect(reveal).toHaveAccessibleName("Скрыть пароль");
  await page.keyboard.press("Space");
  await expect(pass).toHaveAttribute("type", "password");
  await page.keyboard.press("Tab"); // → submit
  await expect(page.getByTestId("login-submit")).toBeFocused();
  await expect(user).toHaveAttribute("autocomplete", "username");
  await expect(pass).toHaveAttribute("autocomplete", "current-password");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/");
  await expect(page.getByTestId("account")).toContainText(E2E_USER);
});

test("wrong credentials: one generic message for unknown users and wrong passwords", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/login");
  const messages: string[] = [];
  for (const username of [E2E_SECOND_USER, "no-such-analyst"]) {
    await page.getByTestId("login-username").fill(username);
    await page.getByTestId("login-password").fill("definitely-not-the-password");
    await page.getByTestId("login-submit").click();
    const error = page.getByTestId("login-error");
    await expect(error).toBeVisible();
    messages.push((await error.textContent())!);
    await expect(page.getByTestId("login-password")).toHaveValue(""); // cleared …
    await expect(page.getByTestId("login-password")).toBeFocused(); // … and ready for a retry
    await expect(page.getByTestId("login-username")).toHaveValue(username);
  }
  expect(messages[0]).toBe("Неверное имя пользователя или пароль.");
  expect(messages[1]).toBe(messages[0]);
  // The password never appears anywhere on the page or in client logs.
  await expect(page.locator("body")).not.toContainText("definitely-not-the-password");
  expect(errors.some((e) => e.includes("definitely-not-the-password"))).toBe(false);
  expect(unexpected(errors, 401)).toEqual([]);
});

test("loading state and double-submit protection", async ({ page }) => {
  let calls = 0;
  await page.route("**/api/v1/auth/login", async (route) => {
    calls += 1;
    await new Promise((r) => setTimeout(r, 700));
    await route.continue();
  });
  await page.goto("/login");
  await page.getByTestId("login-username").fill(E2E_USER);
  await page.getByTestId("login-password").fill(E2E_PASSWORD);
  const submit = page.getByTestId("login-submit");
  await submit.click();
  await expect(submit).toBeDisabled();
  await expect(submit).toHaveText("Выполняется вход…");
  await expect(page.locator("form")).toHaveAttribute("aria-busy", "true");
  await page.getByTestId("login-password").press("Enter"); // a second submit while the first is in flight
  await expect(page).toHaveURL("/");
  expect(calls).toBe(1);
});

test("returns to the requested route, survives reload, and sign-out revokes the session", async ({ page, browser }) => {
  const errors = collectErrors(page);
  await page.goto("/cases?status=new");
  await expect(page).toHaveURL(/\/login\?next=/);
  await signIn(page);
  await expect(page).toHaveURL("/cases?status=new");

  await page.reload();
  await expect(page).toHaveURL("/cases?status=new");
  await expect(page.getByTestId("account")).toContainText("E2E analyst");
  const [cookie] = (await page.context().cookies()).filter((c) => c.name.includes("nexora_session"));
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  // Nothing about the session is kept in web storage.
  const stored = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }));
  expect(stored).not.toContain(cookie!.value);
  expect(stored.toLowerCase()).not.toContain("csrf");

  await page.getByTestId("sign-out").click();
  await expect(page).toHaveURL("/login?reason=signed_out");
  await expect(page.getByTestId("login-notice")).toHaveText("Вы вышли из системы.");

  await page.goto("/alerts");
  await expect(page).toHaveURL(/\/login\?next=%2Falerts/);

  // Replaying the captured cookie from another browser context: the server has revoked it.
  const thief = await browser.newContext();
  await thief.addCookies([cookie!]);
  const replay = await thief.request.get(new URL("/api/v1/auth/me", page.url()).toString());
  expect(replay.status()).toBe(401);
  await thief.close();
  expect(unexpected(errors)).toEqual([]);
});

test("an ended session sends the analyst to sign in and back to where they were", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL("/");
  // Let the overview finish loading first.
  await page.waitForLoadState("networkidle");
  // Whichever API request reaches the server first after the cookies are gone discovers the ended session
  // and sends the analyst to sign in from wherever they are at that moment (correct behaviour). "Network
  // idle" cannot guarantee that request is the one this test means: a late chained fetch or the tab-
  // visibility re-check can land between clearing the cookies and the click, which replaces the whole shell
  // and leaves the click on a detached link (seen in CI run 65; reproduced by dispatching one
  // visibilitychange here). So park every API request until the click has navigated to /lab; the first
  // request that then reaches the server is deterministically one made from /lab.
  let release!: () => void;
  const parked = new Promise<void>((resolve) => (release = resolve));
  await page.route("**/api/**", async (route) => {
    await parked;
    await route.continue();
  });
  // The server-side session disappears (expiry, revocation); the next API call is rejected.
  await page.context().clearCookies();
  await page.getByRole("navigation", { name: "Инструменты" }).getByRole("link", { name: "Лаборатория" }).click();
  await expect(page).toHaveURL("/lab");
  release();
  await expect(page).toHaveURL(/\/login\?next=%2Flab&reason=expired$/);
  await expect(page.getByTestId("login-notice")).toContainText("Сеанс завершён");
  await signIn(page);
  await expect(page).toHaveURL("/lab");
  expect(unexpected(errors, 401)).toEqual([]);
});

test("a session that ends while the next screen is still loading still returns the analyst there", async ({ page }) => {
  // CI run 88: React Router runs navigations in a transition, so while a lazily loaded screen is loading the
  // router still reports the previous location. An expiry discovered in that window used the stale location and
  // dropped the return target (/login?reason=expired instead of ?next=%2Flab). Hold the /lab chunk (dev server
  // module or production asset) so the expiry is discovered exactly inside that window.
  const errors = collectErrors(page);
  await page.goto("/login");
  await signIn(page);
  await expect(page).toHaveURL("/");
  await page.waitForLoadState("networkidle");
  let releaseChunk!: () => void;
  const chunk = new Promise<void>((resolve) => (releaseChunk = resolve));
  await page.route(
    (url) => /fraud-lab|FraudLab/.test(url.pathname),
    async (route) => {
      await chunk;
      await route.continue();
    },
  );
  // As in the test above: no API request may discover the cleared cookies before the click (it would replace the
  // shell under the click). Park them until the navigation to /lab has started.
  let releaseApi!: () => void;
  const parked = new Promise<void>((resolve) => (releaseApi = resolve));
  await page.route("**/api/**", async (route) => {
    await parked;
    await route.continue();
  });
  await page.context().clearCookies();
  await page.getByRole("navigation", { name: "Инструменты" }).getByRole("link", { name: "Лаборатория" }).click();
  await expect(page).toHaveURL("/lab");
  releaseApi();
  // The app's own re-check when the tab becomes visible discovers the ended session while /lab is pending.
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await expect(page).toHaveURL(/\/login\?next=%2Flab&reason=expired$/);
  releaseChunk();
  await expect(page.getByTestId("login-notice")).toContainText("Сеанс завершён");
  await signIn(page);
  await expect(page).toHaveURL("/lab");
  expect(unexpected(errors, 401)).toEqual([]);
});

for (const { name, width, height } of [
  { name: "390", width: 390, height: 844 },
  { name: "1440", width: 1440, height: 900 },
  { name: "1920", width: 1920, height: 1080 },
]) {
  test(`sign-in layout at ${name}px in dark and light themes`, async ({ page }) => {
    const errors = collectErrors(page);
    await page.setViewportSize({ width, height });
    for (const theme of ["dark", "light"] as const) {
      await page.addInitScript((t) => localStorage.setItem("nexora.theme", t), theme);
      await page.goto("/login?reason=expired");
      await expect(page.getByTestId("login-panel")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.dataset.theme ?? "dark")).toBe(theme);
      await noHorizontalOverflow(page);
      // Desktop: the whole form is on screen without scrolling. Phone: it follows the brand header.
      const box = await page.getByTestId("login-submit").boundingBox();
      if (width >= 600) expect(box!.y + box!.height).toBeLessThanOrEqual(height);
      if (shots) await page.screenshot({ path: `${shots}/login-${name}-${theme}.png`, fullPage: true, animations: "disabled" });
    }
    expect(unexpected(errors)).toEqual([]);
  });
}

test("reduced motion: the network illustration is still", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/login");
  const running = await page.evaluate(() => document.getAnimations().filter((a) => (a.effect as KeyframeEffect | null)?.target instanceof SVGElement).length);
  expect(running).toBe(0);
});

test("a viewer reviews everything and is offered no write action (B-011)", async ({ browser }) => {
  // An analyst produces something to look at.
  const analystContext = await browser.newContext();
  const analyst = await analystContext.newPage();
  await analyst.goto("/login");
  await signIn(analyst);
  await seedAndAnalyse(analyst, "7401");
  await analystContext.close();

  const viewerContext = await browser.newContext();
  const page = await viewerContext.newPage();
  const errors = collectErrors(page);
  await page.goto("/login");
  await signIn(page, E2E_VIEWER);
  await expect(page.getByTestId("account-role")).toContainText("Наблюдатель");

  await page.goto("/lab");
  await expect(page.getByTestId("lab-read-only")).toBeVisible();
  await expect(page.getByRole("button", { name: "Сгенерировать набор" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Запустить анализ" })).toHaveCount(0);

  await page.goto("/alerts");
  await page.locator('[data-testid="alert-row"][data-band="high"]').first().click();
  await page.getByTestId("open-investigation").click();
  await expect(page.getByTestId("reasons")).toBeVisible(); // evidence is readable
  await expect(page.getByTestId("open-case")).toHaveCount(0);
  await expect(page.getByTestId("case-read-only")).toBeVisible();
  expect(errors).toEqual([]); // before the deliberate 403 below, which the browser logs

  // The server refuses regardless of what the page shows.
  const status = await page.evaluate(async () => {
    const s = await (await fetch("/api/v1/auth/session")).json();
    const r = await fetch("/api/v1/lab/datasets", {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": s.session.csrf_token },
      body: JSON.stringify({ suite: "demo-v1", seed: 1 }),
    });
    return [r.status, (await r.json()).error.code];
  });
  expect(status).toEqual([403, "FORBIDDEN_ROLE"]);
  await viewerContext.close();
});
