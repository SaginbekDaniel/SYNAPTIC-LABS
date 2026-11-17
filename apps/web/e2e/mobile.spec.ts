import { expect, test } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

test("390px: no horizontal page overflow and primary actions reachable (UI-003)", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "404");
  for (const path of ["/", "/alerts", "/cases", "/lab", "/network"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, path).toBeLessThanOrEqual(390);
  }
  await page.goto("/alerts");
  await page.getByTestId("alert-row").first().click();
  // Single-column order: the case action comes right after the hypothesis, before the graph.
  const action = await page.getByTestId("open-case").boundingBox();
  const graph = await page.locator("#formation-graph").boundingBox();
  expect(action && graph && action.y < graph.y).toBe(true);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  expect(errors).toEqual([]);
});
