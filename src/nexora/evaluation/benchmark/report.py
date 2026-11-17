"""Human-readable rendering of a benchmark report (derived only from report.json)."""

from __future__ import annotations

from typing import Any


def _f(v: Any) -> str:
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return f"{v:.3f}"
    return str(v)


def _ci(ci: list[float] | None) -> str:
    return f"[{ci[0]:.2f}, {ci[1]:.2f}]" if ci else "n/a"


def render_markdown(report: dict[str, Any]) -> str:
    run = report["run"]
    lines = [
        f"# Benchmark report — {run['label']}",
        "",
        f"> {report['disclaimer']}",
        "",
        f"* Benchmark: `{report['suite']['benchmark_version']}`, master seed `{report['suite']['master_seed']}`",
        f"* Code: `{run.get('code_commit')}`{' (uncommitted changes)' if run.get('code_dirty') else ''}",
        f"* Created: {run['created_at']} · duration {run['duration_s']} s",
        f"* Host: {run.get('cpu')} · Python {run.get('python')} · networkx {run.get('networkx')}",
        f"* Splits evaluated: {', '.join(run['splits_evaluated'])}",
        "",
        "## Evaluation units",
        "",
    ]
    lines += [f"* **{k}** — {v}" for k, v in report["evaluation_units"].items()]
    lines += ["", f"Matching rule: {report['matching_rule']['text']}", ""]
    lines += ["## Methods", "", "| Method | Group | Description | Fitted / config |", "|---|---|---|---|"]
    for m in report["methods"]:
        detail = (
            m.get("config_sha256", "")[:12] or f"threshold={_f(m.get('threshold_fitted_on_dev'))} {m.get('params', {})}"
        )
        lines.append(f"| {m['name']} | {m['group']} | {m['description']} | {detail} |")
    for split, methods in report["results"].items():
        lines += [
            "",
            f"## Split `{split}`",
            "",
            "### Scenario unit (primary)",
            "",
            "| Method | TP | FP | FN | TN | Precision (95% CI) | Recall (95% CI) | F1 | FPR | FNR |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, r in methods.items():
            s = r["unit_scenario"]
            lines.append(
                f"| {name} | {s['tp']} | {s['fp']} | {s['fn']} | {s['tn']} "
                f"| {_f(s['precision'])} {_ci(s['ci95']['precision'])}"
                f" | {_f(s['recall'])} {_ci(s['ci95']['recall'])} | {_f(s['f1'])} | {_f(s['fpr'])} | {_f(s['fnr'])} |"
            )
        lines += [
            "",
            "### Alert queue, alert and account units",
            "",
            "| Method | Alerts | Alert precision | Alerts/network | Background alerts/network "
            "| P@10 | P@25 | R@25 | R@50 "
            "| Account precision | Account recall | Latency median / p95 ms |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for name, r in methods.items():
            a, q, acc, lat = r["unit_alert"], r["unit_queue"], r["unit_account"], r["latency_ms"]
            lines.append(
                f"| {name} | {a['raised']} | {_f(a['precision'])} | {_f(a['alerts_per_network'])} "
                f"| {_f(a['background_alerts_per_network'])} | {_f(q['10']['precision'])} | {_f(q['25']['precision'])} "
                f"| {_f(q['25']['recall'])} | {_f(q['50']['recall'])} | {_f(acc['precision'])} | {_f(acc['recall'])} "
                f"| {_f(lat['median'])} / {_f(lat['p95'])} |"
            )
        families = sorted({f for r in methods.values() for f in r["by_family"]})
        names = list(methods)
        lines += [
            "",
            "### By family (detection rate for suspicious, false-positive rate for benign)",
            "",
            "| Family | " + " | ".join(names) + " |",
            "|---|" + "---|" * len(names),
        ]
        for fam in families:
            cells = []
            for n in names:
                fr = methods[n]["by_family"].get(fam)
                cells.append(_f(fr["rate"]) if fr else "")
            lines.append(f"| {fam} | " + " | ".join(cells) + " |")
    if report.get("time_to_detection"):
        lines += ["", "## Time to detection (simulated days)", ""]
        for split, per in report["time_to_detection"].items():
            for name, t in per.items():
                lines.append(
                    f"* `{split}` {name}: median {_f(t['median_days'])} d, max {_f(t['max_days'])} d over "
                    f"{t['detected_networks']} detected networks "
                    f"({t['undetected_networks']} not detected on the full window, "
                    f"{t.get('transient_detections', 0)} of them alerted transiently mid-replay)"
                )
    for section in ("ablations", "robustness"):
        if report.get(section):
            lines += ["", f"## {section.capitalize()}", ""]
            lines += [
                "| Experiment | Split | Precision | Recall | F1 | FPR | Alerts/network | Changed outcomes "
                "| Outcome transitions | Band changes |",
                "|---|---|---|---|---|---|---|---|---|---|",
            ]
            for e in report[section]:
                s = e["metrics"]["unit_scenario"]
                moves = ", ".join(f"{k} x{v}" for k, v in (e.get("transitions") or {}).items()) or "—"
                bands = ", ".join(f"{k} x{v}" for k, v in (e.get("band_changes") or {}).items() if v) or "—"
                lines.append(
                    f"| {e['name']} | {e['split']} | {_f(s['precision'])} | {_f(s['recall'])} | {_f(s['f1'])} "
                    f"| {_f(s['fpr'])} | {_f(e['metrics']['unit_alert']['alerts_per_network'])} "
                    f"| {e.get('changed', 'n/a')} | {moves} | {bands} |"
                )
    if report.get("scale"):
        lines += [
            "",
            "## Scale test (all networks of the split merged into one dataset)",
            "",
            "| Method | Transactions | Accounts | Formations | Wall time s | Partial |",
            "|---|---|---|---|---|---|",
        ]
        for sc in report["scale"]:
            partial = ", ".join(sc["partial_reasons"]) or "no"
            lines.append(
                f"| {sc['method']} | {sc['transactions']} | {sc['accounts']} | {sc['formations']} "
                f"| {sc['wall_seconds']} | {partial} |"
            )
    lines.append("")
    return "\n".join(lines)
