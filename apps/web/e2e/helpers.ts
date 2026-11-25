import { expect, type Page } from "@playwright/test";

// Test-only password for accounts created in the disposable E2E database (scripts/e2e_stack.sh).
export const E2E_PASSWORD = process.env.NEXORA_E2E_PASSWORD ?? "e2e-only-password-disposable-db";
export const E2E_USER = "e2e.analyst";
export const E2E_SECOND_USER = "e2e.second";
export const E2E_VIEWER = "e2e.viewer"; // role viewer (B-011)
export const AUTH_STATE = "e2e/.auth/analyst.json";

/** Sign in through the real form (the page must be on, or redirected to, /login). */
export async function signIn(page: Page, username = E2E_USER, password = E2E_PASSWORD) {
  await expect(page.getByTestId("login-panel")).toBeVisible();
  await page.getByTestId("login-username").fill(username);
  await page.getByTestId("login-password").fill(password);
  await page.getByTestId("login-submit").click();
  await expect(page).not.toHaveURL(/\/login/);
}

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
  // Fail with the API's own error message instead of a bare timeout if the job request is rejected.
  const status = page.getByTestId("job-status");
  const failure = page.locator(".state--error[role=alert]");
  await expect(status.or(failure)).toBeVisible({ timeout: 30_000 });
  if (await failure.isVisible()) throw new Error(`analysis request failed: ${await failure.innerText()}`);
  await expect(status).toContainText("готово", { timeout: 30_000 });
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
