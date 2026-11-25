import { expect, test } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

// B-042: alerts whose networks share accounts are shown as related - in the queue and in the investigation.
// demo-v1 seed 3 contains one network that opened three alerts (see tests/integration/test_api.py).
test("related alerts: marked in the queue and linked from each investigation", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "3");
  await page.getByTestId("to-alerts").click();

  const rows = page.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  const related = rows.filter({ has: page.getByTestId("alert-related") });
  await expect(related).toHaveCount(3);
  await expect(related.first().getByTestId("alert-related")).toHaveText("ещё 2 связанные проверки");
  const total = await rows.count();
  expect(total).toBeGreaterThan(3); // the others stay ungrouped: nothing is merged or hidden

  // Open one of them; the header lists the other two, each a link to its own investigation.
  const href = await related.first().getAttribute("href");
  const firstId = href!.split("/").pop()!;
  await page.goto(href!);
  const list = page.getByTestId("related-alerts");
  await expect(list.getByRole("link")).toHaveCount(2);
  await expect(list.getByRole("link").first()).toContainText(/Воронка|Распределение|Цепочка|Круговое/);

  // Follow a link: the related alert lists the one we came from.
  await list.getByRole("link").first().click();
  await expect(page).not.toHaveURL(new RegExp(firstId));
  await expect(page.getByTestId("related-alerts").locator(`a[href="/alerts/${firstId}"]`)).toHaveCount(1);
  expect(errors).toEqual([]);
});
