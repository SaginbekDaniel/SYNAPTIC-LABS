import { expect, test, type Page } from "@playwright/test";
import { collectErrors } from "../e2e/helpers";

const authConfigured = Boolean(process.env.NEXORA_SMOKE_USER && process.env.NEXORA_SMOKE_PASSWORD);
const shots = process.env.NEXORA_SMOKE_SCREENSHOTS;

async function shot(page: Page, name: string) {
  if (shots) await page.screenshot({ path: `${shots}/${name}.png` });
}

test("gateway: health is public, everything else needs credentials", async ({ baseURL }) => {
  // Plain fetch: carries no configured credentials, unlike Playwright request contexts.
  const anonymous = (path: string, init?: RequestInit) => fetch(new URL(path, baseURL), init).then((r) => r.status);
  expect(await anonymous("/healthz")).toBe(200);
  // API documentation is never served through the gateway.
  for (const path of ["/docs", "/openapi.json"]) {
    expect([401, 404], path).toContain(await anonymous(path));
  }
  if (authConfigured) {
    for (const path of ["/", "/alerts", "/api/v1/datasets", "/health/ready", "/assets/missing.js"]) {
      expect(await anonymous(path), path).toBe(401);
    }
    const write = { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" };
    expect(await anonymous("/api/v1/lab/datasets", write)).toBe(401);
    // A client cannot bypass the gateway by presenting its own gateway token.
    const spoof = { headers: { "X-Nexora-Gateway-Token": "guess" } };
    expect(await anonymous("/api/v1/datasets", spoof)).toBe(401);
  }
});

test("readiness: database reachable and migrated", async ({ request }) => {
  const ready = await request.get("/health/ready");
  expect(ready.status()).toBe(200);
  const body = await ready.json();
  expect(body.database).toBe(true);
  expect(body.migration).toBeTruthy();
});

test("journey: lab → worker analysis → queue → investigation → case decision → audit survives reload", async ({ page }) => {
  const errors = collectErrors(page);
  const seed = String(Date.now() % 1_000_000_000);

  await page.goto("/lab");
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
});

test("light theme renders without errors", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/");
  await page.getByRole("group", { name: "Тема оформления" }).getByRole("button", { name: "Светлая" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.goto("/alerts");
  await page.waitForLoadState("networkidle");
  await shot(page, "review-queue-light");
  expect(errors).toEqual([]);
});
