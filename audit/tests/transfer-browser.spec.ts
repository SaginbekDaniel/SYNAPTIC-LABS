import { expect, test } from "@playwright/test";

const path = "/lab/transfer-protection";
const checkPath = "**/api/v1/demo/transfer-checks";

test("connection interruption cannot present a successful transfer result and retry recovers", async ({ page }) => {
  await page.goto(path);
  const check = page.getByRole("button", { name: "Проверить перевод" });
  const result = page.getByRole("region", { name: "Результат проверки" });
  await expect(check).toBeEnabled();
  await page.route(checkPath, (route) => route.abort("connectionfailed"), { times: 1 });
  await check.click();
  await expect(result.locator("[data-decision]")).toHaveAttribute("data-decision", "UNAVAILABLE");
  await expect(result.getByRole("button", { name: "Продолжить в симуляции" })).toHaveCount(0);
  const response = page.waitForResponse((value) => value.url().endsWith("/api/v1/demo/transfer-checks"));
  await result.getByRole("button", { name: "Повторить проверку" }).click();
  const observed = await response;
  expect(observed.status()).toBe(200);
  const { decision, simulation } = await observed.json();
  expect(simulation).toBe(true);
  await expect(result.locator("[data-decision]")).toHaveAttribute("data-decision", decision);
});

test("keyboard form and alert feed expose accessible names and roles", async ({ page }) => {
  await page.goto(path);
  const amount = page.getByRole("textbox", { name: "Сумма, KZT" });
  await amount.fill("0");
  await amount.press("Enter");
  await expect(amount).toHaveAttribute("aria-invalid", "true");
  await expect(page.getByRole("alert")).toContainText("Введите положительную сумму");
  await amount.fill("18000,01");
  await amount.press("Enter");
  await expect(page.getByRole("region", { name: "Результат проверки" })
    .locator("[aria-live=polite]")).toContainText("Дополнительная проверка не требуется");
  const timing = await page.evaluate(() => {
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming;
    return {
      domContentLoadedMs: nav.domContentLoadedEventEnd,
      loadMs: nav.loadEventEnd,
      transferBytes: nav.transferSize,
      paintMs: Object.fromEntries(performance.getEntriesByType("paint").map((entry) => [entry.name, entry.startTime])),
    };
  });
  console.log(JSON.stringify({ navigation: path, timing }));
});
