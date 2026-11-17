import { expect, test } from "@playwright/test";
import { collectErrors, seedAndAnalyse } from "./helpers";

test("transaction → alert → evidence → case decision → audit survives reload (UI-001)", async ({ page }) => {
  const errors = collectErrors(page);
  let dialog = false;
  page.on("dialog", async (d) => {
    dialog = true;
    await d.dismiss();
  });
  await seedAndAnalyse(page, "2026");
  await page.getByTestId("to-alerts").click();

  const rows = page.getByTestId("alert-row");
  await expect(rows.first()).toBeVisible();
  // The queue never contains low-band items; unresolved boundary cases stay visible.
  await expect(page.locator('[data-testid="alert-row"][data-band="low"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="alert-row"][data-band="insufficient_evidence"]')).toHaveCount(1);

  // Desktop: a row opens a preview first; the investigation is one explicit step away.
  await page.locator('[data-testid="alert-row"][data-band="high"]').first().click();
  await expect(page.getByTestId("alert-preview")).toBeVisible();
  await expect(page).toHaveURL(/[?&]sel=/);
  await page.getByTestId("open-investigation").click();
  await expect(page.getByTestId("reasons")).toBeVisible();
  await expect(page.getByTestId("temporal-facts")).toContainText("только дата");

  // Drill down from a claim to its source transactions.
  await page.getByRole("button", { name: "Показать транзакции" }).first().click();
  await expect(page.locator('#evidence-tx tr[data-highlight="true"]').first()).toBeVisible();

  await page.getByTestId("open-case").click();
  await page.getByTestId("case-action").getByRole("radio", { name: /Взять в работу/ }).check();
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);

  await page.getByTestId("case-action").getByRole("radio", { name: /Эскалировать/ }).check();
  await expect(page.getByTestId("case-submit")).toBeDisabled(); // reason required
  await page.getByTestId("case-reason").fill("Хронология и суммы подтверждены, нужна проверка владельцев");
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("case-decision")).toContainText("Эскалирован");

  const xss = '<img src=x onerror="alert(1)">';
  await page.getByTestId("case-note-input").fill(xss);
  await page.getByRole("button", { name: "Добавить заметку" }).click();
  await expect(page.getByTestId("case-notes")).toContainText(xss); // shown as literal text

  await page.reload();
  await expect(page.getByTestId("case-decision")).toContainText("Эскалирован");
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(4);
  expect(dialog).toBe(false);
  expect(errors).toEqual([]);
});

test("arbitrary account lookup is exact or honestly empty (UI-002)", async ({ page }) => {
  await seedAndAnalyse(page, "11");
  await page.goto("/alerts");
  const first = page.getByTestId("alert-row").first();
  const account = (await first.locator(".alert-row__title code").textContent())!.trim();
  await page.goto(`/network?account=${encodeURIComponent(account)}`);
  await expect(page.locator("#account-summary")).toContainText(account);
  await expect(page.locator("#account-summary")).toContainText("Участие в формациях");

  await page.goto("/network?account=no-such-account-000");
  await expect(page.getByText("Счёт no-such-account-000 не найден")).toBeVisible();
});

test("legitimate lookalikes are not escalated by default", async ({ page }) => {
  await seedAndAnalyse(page, "5", "lookalikes-v1");
  await page.goto("/alerts");
  // Reverse-chronology paths and payroll never reach the queue. A merchant-settlement hub
  // may (known hard negative, reported in docs/LIMITATIONS.md); nothing reaches "critical".
  await expect(page.locator('[data-testid="alert-row"][data-band="critical"]')).toHaveCount(0);
  await expect(page.locator('[data-testid="alert-row"][data-band="low"]')).toHaveCount(0);
});

test("API failure is shown truthfully, not as stale success (UI-004)", async ({ page }) => {
  await page.route("**/api/v1/alerts?**", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: { code: "DATABASE_UNAVAILABLE", message: "database is unavailable; retry later", request_id: "req-test", details: {} } }) }),
  );
  await page.goto("/alerts");
  await expect(page.getByRole("alert")).toContainText("DATABASE_UNAVAILABLE");
  await expect(page.getByRole("button", { name: "Повторить" })).toBeVisible();
  await expect(page.getByTestId("alert-list")).toHaveCount(0);
});
