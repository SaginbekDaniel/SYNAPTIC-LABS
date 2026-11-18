import { expect, request, test, type Page } from "@playwright/test";
import { collectErrors, signIn } from "../e2e/helpers";

const smokeUser = process.env.NEXORA_SMOKE_USER ?? "";
const smokePassword = process.env.NEXORA_SMOKE_PASSWORD ?? "";
const basicMode = Boolean(process.env.NEXORA_SMOKE_BASIC_USER);
test.skip(!smokeUser || !smokePassword, "set NEXORA_SMOKE_USER and NEXORA_SMOKE_PASSWORD (an analyst account)");
const shots = process.env.NEXORA_SMOKE_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png` });
}

test("anonymous: sign-in page, never a Basic prompt; every API and write is refused", async ({ baseURL }) => {
  // No session, and in basic mode no gateway credential either. The test runner applies the config's
  // `use.httpCredentials` to every request context it creates, so override them explicitly with an
  // empty credential (answered with 401 like no credential at all).
  const anon = await request.newContext({ baseURL, httpCredentials: { username: "", password: "" } });
  const status = async (path: string, init?: Parameters<typeof anon.fetch>[1]) => (await anon.fetch(path, init)).status();
  expect(await status("/healthz")).toBe(200);
  for (const path of ["/docs", "/openapi.json", "/health/ready"]) expect([401, 404], path).toContain(await status(path));
  if (basicMode) {
    // Stage 1 of the rollout: the shared Basic credential is still in front of everything.
    for (const path of ["/", "/api/v1/datasets", "/api/v1/auth/session"]) expect(await status(path), path).toBe(401);
  } else {
    const page = await anon.get("/alerts");
    expect(page.status()).toBe(200); // the SPA shell; it renders the sign-in page
    expect(page.headers()["www-authenticate"]).toBeUndefined();
    const session = await anon.get("/api/v1/auth/session");
    expect(await session.json()).toEqual({ authenticated: false, session: null });
    const datasets = await anon.get("/api/v1/datasets");
    expect(datasets.status()).toBe(401);
    expect((await datasets.json()).error.code).toBe("AUTH_REQUIRED");
  }
  const write = { method: "POST", headers: { "Content-Type": "application/json" }, data: { suite: "demo-v1", seed: 1 } };
  expect([401, 403]).toContain(await status("/api/v1/lab/datasets", write));
  // A client cannot bypass the gateway by presenting its own gateway token.
  expect(await status("/api/v1/datasets", { headers: { "X-Nexora-Gateway-Token": "guess" } })).toBe(401);
  await anon.dispose();
});

test("journey: lab → worker analysis → queue → investigation → case decision → audit survives reload", async ({ page }) => {
  const errors = collectErrors(page);
  const seed = String(Date.now() % 1_000_000_000);

  await page.goto("/lab");
  await expect(page).toHaveURL(/\/login\?next=%2Flab/);
  await shot(page, "sign-in");
  await signIn(page, smokeUser, smokePassword);
  await expect(page).toHaveURL(/\/lab$/);
  await page.locator('input[name="suite"][value="demo-v1"]').check();
  await page.getByText("Параметры генерации").click();
  await page.locator('input[name="seed"]').fill(seed);
  await page.getByRole("button", { name: "Сгенерировать набор" }).click();
  await expect(page.getByTestId("import-report")).toBeVisible();
  await shot(page, "fraud-lab");
  await page.getByRole("button", { name: "Запустить анализ" }).click();
  // Completed by the separate worker service, observed through the job API.
  await expect(page.getByTestId("job-status")).toContainText("готово", { timeout: 90_000 });

  await page.goto("/");
  await expect(page.getByTestId("kpi-alerts")).toContainText(/\d+/);
  await page.waitForLoadState("networkidle");
  await shot(page, "overview");

  await page.goto("/alerts");
  const rows = page.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  await page.locator('[data-testid="alert-row"][data-band="high"]').first().click();
  await expect(page.getByTestId("alert-preview")).toBeVisible();
  await shot(page, "review-queue");
  await page.getByTestId("open-investigation").click();
  await expect(page.getByTestId("reasons")).toBeVisible();
  await page.getByRole("button", { name: "Показать транзакции" }).first().click();
  await expect(page.locator('#evidence-tx tr[data-highlight="true"]').first()).toBeVisible();
  await page.locator("#formation-graph").scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForLoadState("networkidle");
  await shot(page, "investigation");
  const investigation = page.url();

  await page.getByTestId("open-case").click();
  await page.getByTestId("case-action").getByRole("radio", { name: /Взять в работу/ }).check();
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);

  // Audit entries name the signed-in analyst, taken from the server session.
  for (const entry of await page.getByTestId("audit-log").locator("li").allTextContents()) expect(entry).toContain(smokeUser);

  // The session survives a reload.
  await page.reload();
  await expect(page).toHaveURL(investigation);
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);

  await page.goto("/evaluation");
  await expect(page.getByTestId("split-meta")).toBeVisible();
  await page.waitForLoadState("networkidle");
  await shot(page, "evaluation");

  // Hard refresh on a deep link is served by the SPA fallback.
  await page.goto("/network");
  await page.reload();
  await expect(page.locator("#root")).not.toBeEmpty();
  expect(errors, "console errors / CSP violations").toEqual([]);

  // Sign out: the server revokes the session; the captured cookie no longer opens anything.
  const [cookie] = (await page.context().cookies()).filter((c) => c.name.includes("nexora_session"));
  expect(cookie?.httpOnly).toBe(true);
  expect(cookie?.sameSite).toBe("Strict");
  if (page.url().startsWith("https:")) expect(cookie?.secure && cookie.name.startsWith("__Host-")).toBe(true);
  await page.getByTestId("sign-out").click();
  await expect(page).toHaveURL(/\/login\?reason=signed_out$/);
  await page.goto("/alerts");
  await expect(page).toHaveURL(/\/login\?next=%2Falerts/);
  const replay = await page.context().request.fetch("/api/v1/datasets", { headers: { Cookie: `${cookie!.name}=${cookie!.value}` } });
  expect(replay.status()).toBe(401);
});

test("light theme renders without errors", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await signIn(page, smokeUser, smokePassword);
  await page.getByRole("group", { name: "Тема оформления" }).getByRole("button", { name: "Светлая" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.goto("/alerts");
  await page.waitForLoadState("networkidle");
  await shot(page, "review-queue-light");
  expect(errors).toEqual([]);
});
