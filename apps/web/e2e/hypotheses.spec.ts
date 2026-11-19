import { expect, test } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

test("investigation shows competing explanations with tests, untestable alternatives and next data", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "7001");
  await page.goto("/alerts?kind=funnel");
  // demo-v1 seed 7001: the high-band funnel is a planted one-off collection.
  const row = page.locator('[data-testid="alert-row"][data-band="high"]').first();
  await page.goto((await row.getAttribute("href"))!);

  const section = page.getByTestId("hypotheses");
  await expect(section).toBeVisible();
  await expect(page.getByTestId("hyp-verdict")).toContainText("подозрительной гипотезой");
  // A favoured suspicious reading never reads as proof: untestable alternatives stay listed.
  await expect(page.getByTestId("hyp-verdict")).toContainText("не исключены");
  await expect(page.getByTestId("hyp-one_off_legitimate_collection")).toContainText("Не проверяется по транзакциям");
  await expect(page.getByTestId("hyp-next")).toContainText("вид деятельности");

  // Each hypothesis exposes its falsification tests on demand, with the observation group.
  const business = page.getByTestId("hyp-recurring_business_activity");
  await business.getByText(/Проверки:/).click();
  await expect(business.locator(".reason").first()).toBeVisible();
  await expect(business).toContainText("связи с контрагентами");

  // The verdict is not duplicated in the reasons list once it has its own section.
  await expect(page.getByTestId("reasons")).not.toContainText("Сравнение объяснений");
  expect(errors).toEqual([]);
});

test("a dataset created in the lab stays selected after navigation", async ({ page }) => {
  await seedAndAnalyse(page, "7006", "lookalikes-v1");
  await seedAndAnalyse(page, "7001");
  await page.goto("/");
  // The overview shows the dataset just generated, not the previously newest one.
  await expect(page.getByRole("combobox", { name: "Набор данных" }).locator("option:checked")).toHaveText(/seed 7001/);
});
