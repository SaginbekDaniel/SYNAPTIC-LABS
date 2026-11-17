import { expect, test } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

test("overview answers what needs attention and leads into the top investigation", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "7001");
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Обзор" })).toBeVisible();
  // KPI and donut come from the API; the donut legend lists every band with its count.
  await expect(page.getByTestId("kpi-alerts")).toContainText(/\d+/);
  await expect(page.locator("#risk").getByRole("button", { name: /Высокий: \d+/ })).toBeVisible();
  // The activity chart exposes its data as a table for assistive technology.
  await expect(page.locator("#activity table")).toHaveCount(1);
  await page.getByTestId("lead-action").click();
  await expect(page).toHaveURL(/\/alerts\/[0-9a-f-]+$/);
  await expect(page.getByTestId("reasons")).toBeVisible();
  expect(errors).toEqual([]);
});

test("queue filters persist in the URL and survive reload", async ({ page }) => {
  await seedAndAnalyse(page, "7002");
  await page.goto("/alerts");
  await page.getByRole("group", { name: "Приоритет" }).getByRole("button", { name: /Высокий/ }).click();
  await expect(page).toHaveURL(/band=high/);
  const rows = page.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  await expect(page.locator('[data-testid="alert-row"]:not([data-band="high"])')).toHaveCount(0);
  await page.reload();
  await expect(page.locator('[data-testid="alert-row"]:not([data-band="high"])')).toHaveCount(0);
  await page.getByRole("searchbox").fill("no-such-account");
  await expect(page.getByText("Ничего не найдено")).toBeVisible();
  await page.getByRole("button", { name: "Сбросить фильтры" }).click();
  await expect(page).not.toHaveURL(/band=/);
});

test("investigation: select an account, then end the case with an explicit confirmation", async ({ page }) => {
  const errors = collectErrors(page);
  await seedAndAnalyse(page, "7003");
  await page.goto("/alerts");
  const href = await page.getByTestId("alert-row").first().getAttribute("href");
  await page.goto(href!);
  // Keyboard-reachable path to graph selection: the participant list.
  await page.getByText(/Все счета формации/).click();
  await page.locator(".participant").first().click();
  await expect(page.getByTestId("ctx-account")).toBeVisible();
  await expect(page.getByTestId("ctx-account")).toContainText("В этой формации");
  await page.getByRole("button", { name: "К сводке" }).click();
  await expect(page.getByTestId("reasons")).toBeVisible();

  await page.getByTestId("open-case").click();
  await page.getByTestId("case-action").getByRole("radio", { name: /Взять в работу/ }).check();
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);
  await page.getByTestId("case-action").getByRole("radio", { name: /Отклонить гипотезу/ }).check();
  await page.getByTestId("case-reason").fill("Оборот типичен для группы сравнения");
  await page.getByTestId("case-submit").click();
  // Ending the case asks once more before anything is written.
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("case-decision")).toContainText("Отклонён");
  await expect(page.getByRole("status").filter({ hasText: "Записано в журнал" })).toBeVisible();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(3);
  expect(errors).toEqual([]);
});

test("theme choice applies immediately and persists", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).not.toHaveAttribute("data-theme", "light");
  await page.getByRole("group", { name: "Тема оформления" }).getByRole("button", { name: "Светлая" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
