import { expect, test, type Page } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

const SHOTS = process.env.NEXORA_SHOTS_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

async function stageSettled(page: Page) {
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  // cose settles off-screen and moves once; give the single end-animation time to finish.
  await page.waitForTimeout(900);
}

test("overview: server-ranked formations, snapshot identity, keyboard selection and expansion", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "3101");
  await page.goto("/network");
  await expect(page.getByTestId("graph-snapshot")).toContainText("risk-policy");
  await expect(page.locator("#graph-formations")).toBeVisible();
  await stageSettled(page);
  await shot(page, "graph-overview-1440-dark");

  // Keyboard: focus the stage, step to the top-priority account, select it, then expand it.
  const canvas = page.getByTestId("graph-canvas");
  const before = await canvas.getAttribute("aria-label");
  await canvas.focus();
  await page.keyboard.press("]");
  const announced = page.locator(".graph-stage [aria-live=polite]").first();
  await expect(announced).toContainText("Счёт ");
  await page.keyboard.press("Enter");
  await expect(page.locator("#account-summary")).toBeVisible();
  await expect(page.locator("#account-summary")).toContainText("Участие в формациях");
  // Expansion is a bounded read for exactly the announced account; the drawing can only grow.
  const id = (await announced.innerText()).replace(/^Счёт /, "").split(",")[0]!.trim();
  const expansion = page.waitForResponse((r) => r.url().includes("/graph?") && r.url().includes("mode=local") && new URL(r.url()).searchParams.get("account_id") === id);
  await page.keyboard.press("e");
  expect((await expansion).status()).toBe(200);
  const count = (label: string | null) => Number(/(\d+)/.exec(label ?? "")?.[1] ?? 0);
  await expect.poll(async () => count(await canvas.getAttribute("aria-label"))).toBeGreaterThanOrEqual(count(before));
  await expect(page.getByText("Не удалось загрузить связи счёта")).toHaveCount(0);
  await shot(page, "graph-overview-expanded-1440-dark");
  expect(errors).toEqual([]);
});

test("table fallback: every edge opens its exact source transactions", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "3102");
  await page.goto("/network");
  await page.getByRole("group", { name: "Представление" }).getByRole("button", { name: "Таблица" }).click();
  const table = page.getByTestId("graph-table");
  await expect(table).toBeVisible();
  const row = table.locator("tbody tr").first();
  const count = Number((await row.locator("td").nth(3).innerText()).trim());
  await row.getByRole("button", { name: "Открыть" }).click();
  const detail = page.locator("#edge-detail");
  await expect(detail).toBeVisible();
  await expect(detail.locator("tbody tr")).toHaveCount(Math.min(count, 10));
  await shot(page, "graph-edge-detail-1440-dark");
  expect(errors).toEqual([]);
});

test("filters live in the URL and only select stored formations", async ({ page }) => {
  await seedAndAnalyse(page, "3103");
  await page.goto("/network");
  await page.getByRole("group", { name: "Приоритет" }).getByRole("button", { name: "Средний" }).click();
  await expect(page).toHaveURL(/band=medium/);
  const list = page.locator("#graph-formations");
  await expect(list).toBeVisible();
  await expect(list.locator(".badge--high, .badge--critical, .badge--low")).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("group", { name: "Приоритет" }).getByRole("button", { name: "Средний" })).toHaveAttribute("aria-pressed", "true");
});

test("the same snapshot draws the same picture on every load", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await seedAndAnalyse(page, "3104");
  await page.goto("/network");
  await stageSettled(page);
  const first = await page.getByTestId("graph-canvas").screenshot();
  await page.reload();
  await stageSettled(page);
  const second = await page.getByTestId("graph-canvas").screenshot();
  expect(second.equals(first)).toBe(true);
});

test("light theme and narrow widths keep the workspace usable", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "3105");
  await page.goto("/network");
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await stageSettled(page);
  await shot(page, "graph-overview-1440-light");
  for (const width of [768, 390]) {
    await page.setViewportSize({ width, height: 900 });
    await page.waitForTimeout(300);
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(width);
    await shot(page, `graph-overview-${width}-light`);
  }
  expect(errors).toEqual([]);
});
