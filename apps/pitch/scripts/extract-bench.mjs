// Copies the holdout figures slide 5 needs from the committed benchmark artifact, verbatim.
// Usage: node scripts/extract-bench.mjs   (run from apps/pitch; rerun whenever bench-v1.json changes)
import { readFileSync, writeFileSync } from "node:fs";

const SRC = "../../benchmarks/results/bench-v1.json";
const d = JSON.parse(readFileSync(SRC, "utf8"));
const pick = (m) => {
  const r = d.results.holdout[m];
  return { scenario: r.scenario, alerts: r.alerts, queue: r.queue, by_family: r.by_family };
};
const out = {
  source: "benchmarks/results/bench-v1.json (main)",
  split: "holdout",
  datasets: d.splits.holdout.datasets,
  code_commit: d.code.commit,
  code_dirty: d.code.dirty,
  synthetic: d.synthetic,
  config: d.config,
  methods: {
    nexora_v2: d.methods.find((m) => m.id === "nexora_v2"),
    B1_rules: d.methods.find((m) => m.id === "B1_rules"),
  },
  results: { nexora_v2: pick("nexora_v2"), B1_rules: pick("B1_rules") },
};
writeFileSync("src/data/bench-excerpt.json", JSON.stringify(out, null, 1) + "\n");
console.log("wrote src/data/bench-excerpt.json");
