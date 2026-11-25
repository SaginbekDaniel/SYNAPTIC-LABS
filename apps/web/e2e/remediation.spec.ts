import { expect, test } from "@playwright/test";

const CSV = [
  "source_transaction_id,sender_account_id,receiver_account_id,amount_minor,currency,occurred_at",
  "a,alpha,beta,8000000,KZT,2026-11-01T12:00:00Z",
  "b,beta,gamma,8000000,KZT,2026-11-02T12:00:00Z",
  "c,gamma,alpha,8000000,KZT,2026-11-03T12:00:00Z",
  "bad,gamma,delta,-5,KZT,2026-11-03T12:00:00Z",
].join("\n");

test("CSV upload reports quarantine, analyses the records, and opens an audited case", async ({ page }) => {
  await page.goto("/lab");
  await page.getByText("Импорт CSV", { exact: true }).click();
  await page.getByLabel("Файл с операциями (CSV)").setInputFiles({
    name: "remediation-cycle.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(CSV),
  });
  await page.getByRole("button", { name: "Загрузить CSV" }).click();
  await expect(page.getByTestId("csv-import-status")).toContainText("Импорт завершён");
  await expect(page.getByTestId("import-report")).toContainText("3");
  await expect(page.getByText(/Строка 4/)).toBeVisible();
  await page.getByRole("button", { name: "Запустить анализ" }).click();
  await expect(page.getByTestId("job-status")).toContainText("готово");
  await page.getByTestId("to-alerts").click();
  await page.getByTestId("alert-row").first().click();
  await page.getByTestId("open-investigation").click();
  await expect(page.getByTestId("reasons")).toBeVisible();
  await page.getByTestId("open-case").click();
  await page.getByTestId("case-action").getByRole("radio", { name: /Взять в работу/ }).check();
  await page.getByTestId("case-submit").click();
  await expect(page.getByTestId("audit-log").locator("li")).toHaveCount(2);
});

test("durable sandbox step-up, protected evidence and saved result survive reload", async ({ page }) => {
  await page.goto("/lab/transfer-protection/sandbox");
  const customer = process.env.NEXORA_E2E_SANDBOX_CUSTOMER!;
  const reviewer = process.env.NEXORA_E2E_SANDBOX_REVIEWER!;
  const token = page.getByLabel("Токен пользователя песочницы");
  const status = page.getByTestId("sandbox-result");
  await token.fill(customer);
  const assessmentResponse = page.waitForResponse((response) =>
    response.url().endsWith("/api/v1/sandbox/transfers") && response.request().method() === "POST");
  await page.getByRole("button", { name: "Проверить перевод" }).click();
  const assessment = await (await assessmentResponse).json();
  await expect(page.getByTestId("transfer-risk-band")).toHaveAttribute("data-band", assessment.risk_band);
  await expect(status).toContainText(assessment.customer_message);
  await expect(status).toHaveAttribute("data-status", "STEP_UP_REQUIRED");
  await expect(page).toHaveURL(/sandbox\/[0-9a-f-]{36}$/);
  await page.reload();
  await token.fill(reviewer);
  await page.getByRole("button", { name: "Доказательства для аналитика" }).click();
  await expect(page.getByText("Операций в доказательствах", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: "Подтвердить дополнительную проверку" }).click();
  await expect(status).toHaveAttribute("data-status", "READY");
  await token.fill(customer);
  await page.getByRole("button", { name: "Открыть сохранённую оценку" }).click();
  await page.getByRole("button", { name: "Подтвердить в песочнице" }).click();
  await expect(status).toHaveAttribute("data-status", "SIMULATED_COMPLETED");
  await expect(status).toContainText("Действие подтверждено в песочнице");
});
