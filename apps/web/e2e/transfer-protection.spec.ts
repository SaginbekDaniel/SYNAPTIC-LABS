import { expect, test } from "@playwright/test";

const TITLE = "NEXORA Transfer Protection";
const PATH = "/lab/transfer-protection";

test("transfer recommendations, simulation and analyst authorization", async ({ page }) => {
  await page.goto(PATH);
  await expect(page.getByRole("heading", { name: TITLE })).toBeVisible();
  const scenario = page.getByRole("combobox", { name: "Сценарий" });
  const check = page.getByRole("button", { name: "Проверить перевод" });
  const result = page.getByRole("region", { name: "Результат проверки" });
  const continueSimulation = result.getByRole("button", { name: "Продолжить в симуляции" });
  await page.getByRole("textbox", { name: "Сумма, KZT" }).fill("0");
  await check.click();
  await expect(page.getByRole("alert")).toContainText("Введите положительную сумму");
  await page.getByRole("textbox", { name: "Сумма, KZT" }).fill("18000,01");
  await check.click();
  await expect(result).toContainText("Дополнительная проверка не требуется");
  await continueSimulation.click();
  await expect(result).toContainText("Демо-перевод выполнен в симуляции");
  await expect(continueSimulation).toHaveCount(0);

  await scenario.selectOption("merchant");
  await check.click();
  await expect(result).toContainText("операциями из демо-реестра");
  await scenario.selectOption("limited");
  await check.click();
  await expect(result).toContainText("Недостаточно данных");
  await expect(continueSimulation).toHaveCount(0);

  await scenario.selectOption("mule");
  await check.click();
  await expect(result).toContainText("Проверьте получателя");
  await result.getByRole("button", { name: "Сверить реквизиты" }).click();
  await expect(page.getByRole("heading", { name: "Реквизиты перевода" })).toBeFocused();
  await result.getByRole("button", { name: "Как связаться с банком" }).click();
  await expect(result).toContainText("официальное приложение банка");
  await result.getByRole("button", { name: "Отменить перевод" }).click();
  await expect(result).toContainText("Демо-перевод отменён");

  await scenario.selectOption("replay_early");
  await check.click();
  await expect(result).toContainText("Дополнительная проверка не требуется");
  await scenario.selectOption("replay_late");
  await check.click();
  await expect(result).toContainText("Требуется дополнительная проверка");
  await expect(continueSimulation).toHaveCount(0);
  await result.getByRole("link", { name: "Открыть расследование" }).click();
  await expect(page.getByRole("heading", { name: "Расследование проверки перевода" })).toBeVisible();
  const token = page.getByLabel("Токен доступа аналитика");
  const open = page.getByRole("button", { name: "Показать доказательства" });
  await token.fill("invalid");
  await open.click();
  await expect(page.getByRole("alert")).toContainText("Доступ не предоставлен");
  await expect(page.getByRole("heading", { name: "Граф связанных операций" })).toHaveCount(0);
  await token.fill(process.env.NEXORA_E2E_TRANSFER_TOKEN!);
  await open.click();
  await expect(page.getByRole("heading", { name: "Граф связанных операций" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Хронология доказательств" })).toBeVisible();
  await expect(page.getByText("Подтверждение из отдельного демо-реестра")).toBeVisible();

  await page.getByRole("link", { name: "К проверке перевода" }).click();
  await scenario.selectOption("timeout");
  await check.click();
  await expect(result).toContainText("Время ожидания проверки истекло");
  await expect(result.getByRole("button", { name: "Повторить проверку" })).toBeEnabled();
  await expect(result.getByRole("link", { name: "Открыть расследование" })).toHaveCount(0);
});
