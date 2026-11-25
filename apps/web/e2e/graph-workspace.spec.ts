import { expect, test, type Page } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

const SHOTS = process.env.NEXORA_SHOTS_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png` });
}

async function stageSettled(page: Page) {
  const canvas = page.getByTestId("graph-canvas");
  // The force layout runs in a worker; the drawn graph exists once the canvas reports "ready".
  await expect(canvas).toHaveAttribute("data-layout", "ready", { timeout: 30_000 });
  await expect(canvas).toHaveCSS("opacity", "1");
  await expect(canvas.locator("canvas").first()).toBeVisible();
}

/** A deterministic connected graph of `n` accounts in the API's shape (a tree plus n/2 extra transfers). */
function syntheticGraph(n: number) {
  let s = n >>> 0;
  const rnd = () => (s = (s * 1664525 + 1013904223) >>> 0) / 2 ** 32;
  const nodes = Array.from({ length: n }, (_, i) => ({ account_id: `acc-${i}`, hop: null, is_boundary: false, formations: [], band: null, priority: null }));
  const edges: Record<string, unknown>[] = [];
  const seen = new Set<string>();
  const add = (a: number, b: number) => {
    const key = `${a}>${b}`;
    if (a === b || seen.has(key)) return;
    seen.add(key);
    edges.push({ kind: "observed_transfer", sender: `acc-${a}`, receiver: `acc-${b}`, currency: "KZT", amount_minor: String(1000 + edges.length), n_transactions: 1, first_date: "2026-07-01", last_date: "2026-07-01", evidence_formation_ids: [], temporal_statuses: [] });
  };
  for (let i = 1; i < n; i++) add(i, Math.floor(rnd() * i));
  for (let i = 0; i < n / 2; i++) add(Math.floor(rnd() * n), Math.floor(rnd() * n));
  return { nodes, edges };
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
  // Closed on arrival (the graph comes first, H-23); the analyst opens them.
  const filters = page.locator("details.graph-filters");
  await expect(filters).not.toHaveAttribute("open", "");
  await filters.locator("summary").click();
  await page.getByRole("group", { name: "Приоритет" }).getByRole("button", { name: "Средний" }).click();
  await expect(page).toHaveURL(/band=medium/);
  const list = page.locator("#graph-formations");
  await expect(list).toBeVisible();
  await expect(list.locator(".badge--high, .badge--critical, .badge--low")).toHaveCount(0);
  await page.reload();
  // An active filter opens them by itself and is counted in the summary, so a filtered view is never hidden.
  await expect(filters).toHaveAttribute("open", "");
  await expect(filters.locator(".graph-filters__count")).toHaveText("1");
  await expect(page.getByRole("group", { name: "Приоритет" }).getByRole("button", { name: "Средний" })).toHaveAttribute("aria-pressed", "true");
});

test("the graph is on screen on arrival at 1440 × 900 (H-23)", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await seedAndAnalyse(page, "3107");
  await page.goto("/network");
  await stageSettled(page);
  const stage = (await page.getByTestId("graph-canvas").boundingBox())!;
  // Before the fix the stage began at y ≈ 580 and 57 % of it was visible; now most of the drawing is in view.
  expect(stage.y).toBeLessThanOrEqual(520);
  expect((900 - stage.y) / stage.height).toBeGreaterThanOrEqual(0.7);
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

test("a 300-account view lays out in a worker: the main thread stays responsive (H-04)", async ({ page }) => {
  test.setTimeout(120_000);
  const errors = collectErrors(page);
  await page.addInitScript(() => {
    const w = window as unknown as { __longTasks: { start: number; duration: number }[] };
    w.__longTasks = [];
    new PerformanceObserver((list) => list.getEntries().forEach((e) => w.__longTasks.push({ start: e.startTime, duration: e.duration }))).observe({
      type: "longtask",
      buffered: true,
    });
  });
  await seedAndAnalyse(page, "3106");
  // The synthetic suites never reach 300 accounts in one view: serve the real response for this snapshot
  // with 300 accounts and 449 transfers in place of its own.
  await page.route("**/api/v1/snapshots/*/graph?**", async (route) => {
    const body = await (await route.fetch()).json();
    await route.fulfill({ json: { ...body, ...syntheticGraph(300), formations: [], limits: { ...body.limits, max_nodes: 400, truncated: false, reasons: [] } } });
  });
  await page.goto("/network");
  await stageSettled(page);
  await expect(page.getByTestId("graph-canvas")).toHaveAttribute("aria-label", /300 счетов, 449 связей/);

  const timing = await page.evaluate(() => {
    const mark = (name: string) => performance.getEntriesByName(name, "mark")[0]?.startTime ?? null;
    const w = window as unknown as { __longTasks: { start: number; duration: number }[] };
    return { start: mark("nexora:graph-layout:start"), end: mark("nexora:graph-layout:end"), tasks: w.__longTasks };
  });
  expect(timing.start).not.toBeNull();
  expect(timing.end).not.toBeNull();
  const [start, end] = [timing.start!, timing.end!];
  // While the worker computes, no task blocks the main thread for more than 200 ms ...
  const during = timing.tasks.filter((t) => t.start >= start && t.start + t.duration <= end);
  expect(during.filter((t) => t.duration > 200)).toEqual([]);
  // ... and nothing from navigation to a drawn graph blocks for a second (synchronous cose: 2.5 s at 200 accounts).
  expect(timing.tasks.filter((t) => t.duration >= 1000)).toEqual([]);

  // Back to the same view: the stored positions are reused, no new layout starts.
  const layoutsStarted = () => page.evaluate(() => performance.getEntriesByName("nexora:graph-layout:start", "mark").length);
  const before = await layoutsStarted();
  await page.getByRole("button", { name: "Таблица" }).click();
  await page.getByRole("button", { name: "Граф", exact: true }).click();
  await stageSettled(page);
  expect(await layoutsStarted()).toBe(before);
  expect(errors).toEqual([]);
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
