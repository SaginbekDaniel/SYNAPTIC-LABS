import { expect, test } from "@playwright/test";
import { seedAndAnalyse } from "./helpers";

// Regression: with a dataset already present, generating another one in the Lab used to snap the
// active dataset back to the previous one (the fallback ran against the not-yet-refreshed list), so
// "go to alerts" showed the old dataset's queue.
test("a newly generated dataset becomes and stays the active dataset", async ({ page }) => {
  await seedAndAnalyse(page, "8101");
  await seedAndAnalyse(page, "8102");
  const selector = page.getByRole("combobox", { name: "Набор данных" });
  await expect(selector.locator("option:checked")).toContainText("seed 8102");
  await page.getByTestId("to-alerts").click();
  await expect(page.getByTestId("alert-row").first()).toBeVisible();
  await expect(selector.locator("option:checked")).toContainText("seed 8102");
  await page.reload();
  await expect(selector.locator("option:checked")).toContainText("seed 8102");
});
