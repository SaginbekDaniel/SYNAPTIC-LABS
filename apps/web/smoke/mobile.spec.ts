import { expect, test } from "@playwright/test";
import { collectErrors } from "../e2e/helpers";

test("390px: core screens fit the viewport", async ({ page }) => {
  const errors = collectErrors(page);
  for (const path of ["/", "/alerts", "/lab", "/evaluation"]) {
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    const width = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(width, path).toBeLessThanOrEqual(390);
  }
  if (process.env.NEXORA_SMOKE_SCREENSHOTS) {
    await page.goto("/alerts");
    await page.waitForLoadState("networkidle");
    await page.screenshot({ path: `${process.env.NEXORA_SMOKE_SCREENSHOTS}/mobile-queue.png` });
  }
  expect(errors).toEqual([]);
});
