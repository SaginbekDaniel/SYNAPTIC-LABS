import { expect, test } from "@playwright/test";
import { collectErrors, signIn } from "../e2e/helpers";

test("390px: sign-in and core screens fit the viewport", async ({ page }) => {
  test.skip(!process.env.NEXORA_SMOKE_USER, "set NEXORA_SMOKE_USER and NEXORA_SMOKE_PASSWORD");
  const errors = collectErrors(page);
  await page.goto("/");
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  await signIn(page, process.env.NEXORA_SMOKE_USER, process.env.NEXORA_SMOKE_PASSWORD);
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
