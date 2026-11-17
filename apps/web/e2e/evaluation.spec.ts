import { expect, test } from "@playwright/test";
import { collectErrors } from "./helpers";

interface Report {
  label: string;
  methods: { name: string; group: string }[];
  results: { split: string; method: string; scenario: { f1: number | null; tp: number } }[];
  run: { splits_evaluated: string[] };
}

const percent = (v: number) => `${(v * 100).toLocaleString("ru-RU", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} %`;

test("evaluation screen renders the recorded benchmark, not invented numbers", async ({ page, request }) => {
  const errors = collectErrors(page);
  const runs = await (await request.get("/api/v1/evaluation/runs")).json();
  const report: Report = await (await request.get(`/api/v1/evaluation/runs/${runs.latest}`)).json();
  const split = report.run.splits_evaluated.includes("test") ? "test" : report.run.splits_evaluated.at(-1)!;
  const primary = report.methods.filter((m) => m.group === "nexora").at(-1)!.name;
  const expected = report.results.find((r) => r.split === split && r.method === primary)!;

  await page.goto("/evaluation");
  await expect(page.getByTestId("eval-disclaimer")).toBeVisible();
  await expect(page.getByTestId("eval-kpi-f1").locator(".kpi__value")).toHaveText(percent(expected.scenario.f1!));
  const rows = page.getByTestId("eval-scenario-table").locator("tbody tr");
  await expect(rows).toHaveCount(report.results.filter((r) => r.split === split).length);

  // Changing the split re-reads the same report and updates the URL (deep-linkable).
  const other = report.run.splits_evaluated.find((s) => s !== split)!;
  await page.getByTestId("eval-split").selectOption(other);
  await expect(page).toHaveURL(new RegExp(`split=${other}`));
  const otherTp = report.results.find((r) => r.split === other && r.method === primary)!.scenario.tp;
  await expect(rows.last().locator("td").first()).toHaveText(String(otherTp));
  expect(errors).toEqual([]);
});
