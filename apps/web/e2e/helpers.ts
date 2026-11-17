import { expect, type Page } from "@playwright/test";

/** Generate a synthetic suite through the UI and wait for the real worker to publish it. */
export async function seedAndAnalyse(page: Page, seed: string, suite = "demo-v1") {
  await page.goto("/lab");
  await page.locator(`input[name="suite"][value="${suite}"]`).check();
  // Seed and precision live behind the "advanced settings" disclosure.
  await page.getByText("Параметры генерации").click();
  await page.locator('input[name="seed"]').fill(seed);
  await page.getByRole("button", { name: "Сгенерировать набор" }).click();
  await expect(page.getByTestId("import-report")).toBeVisible();
  await page.getByRole("button", { name: "Запустить анализ" }).click();
  await expect(page.getByTestId("job-status")).toContainText("готово", { timeout: 30_000 });
  await expect(page.getByTestId("to-alerts")).toBeVisible();
}

export function collectErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  return errors;
}
