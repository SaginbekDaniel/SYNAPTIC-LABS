import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { collectErrors } from "./helpers";

// The screen must show the numbers of the committed benchmark run (ratios rounded once from its counts),
// not anything recomputed from transactions in the browser.
const artifact = JSON.parse(readFileSync(new URL("../../../benchmarks/results/bench-v1.json", import.meta.url), "utf-8"));

test("evaluation screen renders the persisted benchmark run, labelled synthetic", async ({ page }) => {
  const errors = collectErrors(page);
  await page.goto("/evaluation");
  await expect(page.getByRole("heading", { name: "Оценка качества" })).toBeVisible();
  await expect(page.getByRole("note")).toContainText("синтетические");

  // Holdout is the default view; the headline is NEXORA v2's holdout recall from its counts,
  // tp/(tp+fn) = 73/92 = 79,348 %, rounded once (the stored ratio 0.7935 re-rounded would read 79,4 %).
  await expect(page.getByRole("button", { name: "Отложенная" })).toHaveAttribute("aria-pressed", "true");
  const { tp, fn } = artifact.results.holdout.nexora_v2.scenario as { tp: number; fn: number };
  expect([tp, fn]).toEqual([73, 19]);
  await expect(page.getByTestId("kpi-recall").locator(".stat__value")).toHaveText("79,3 %");

  const methods = page.getByTestId("eval-methods-table");
  await expect(methods.getByRole("row")).toHaveCount(1 + artifact.methods.length);
  await expect(methods).toContainText("B1 · Правила мониторинга");
  await expect(page.getByTestId("eval-run")).toContainText(String(artifact.code.commit).slice(0, 12));
  await expect(page.getByTestId("eval-fp")).toBeVisible();

  await page.getByRole("button", { name: "Валидация" }).click();
  await expect(page.getByTestId("split-meta")).toContainText("seed 2000–2019");
  expect(errors).toEqual([]);
});
