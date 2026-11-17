import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { collectErrors } from "./helpers";

// The screen must show the numbers of the committed benchmark run, not anything computed in the browser.
const artifact = JSON.parse(readFileSync(new URL("../../../benchmarks/results/bench-v1.json", import.meta.url), "utf-8"));
const pct = (v: number) => `${(Math.round(v * 1000) / 10).toLocaleString("ru-RU", { maximumFractionDigits: 1 })} %`;

test("evaluation screen renders the persisted benchmark run, labelled synthetic", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { name: "Оценка качества" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("синтетические");

  // Holdout is the default view; the headline equals the artifact's holdout recall for NEXORA v2.
  await expect(page.getByRole("button", { name: "Отложенная" })).toHaveAttribute("aria-pressed", "true");
  const recall = artifact.results.holdout.nexora_v2.scenario.recall as number;
  await expect(page.getByTestId("kpi-recall")).toContainText(pct(recall));

  const methods = page.getByTestId("eval-methods-table");
  await expect(methods.getByRole("row")).toHaveCount(1 + artifact.methods.length);
  await expect(methods).toContainText("B1 · Правила мониторинга");
  await expect(page.getByTestId("eval-run")).toContainText(String(artifact.code.commit).slice(0, 12));
  await expect(page.getByTestId("eval-fp")).toBeVisible();

  await page.getByRole("button", { name: "Валидация" }).click();
  await expect(page.getByTestId("split-meta")).toContainText("seed 2000–2019");
  expect(errors).toEqual([]);
});
