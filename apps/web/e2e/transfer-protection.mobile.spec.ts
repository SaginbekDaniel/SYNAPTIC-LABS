import { expect, test } from "@playwright/test";

test("mobile transfer simulator is reachable and fits the viewport", async ({ page }) => {
  await page.goto("/lab");
  await page.getByRole("button", { name: "Ещё" }).click();
  await page.getByRole("link", { name: "Защита переводов" }).click();
  await expect(page.getByRole("heading", { name: "NEXORA Transfer Protection" })).toBeVisible();
  await page.getByRole("combobox", { name: "Сценарий" }).selectOption("review");
  await page.getByRole("button", { name: "Проверить перевод" }).click();
  await expect(page.getByText("Требуется дополнительная проверка", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
});
