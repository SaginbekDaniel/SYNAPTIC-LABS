"""Render the README benchmark figure from the committed artifact.

Reads benchmarks/results/bench-v1.json (holdout split) and writes
docs/assets/readme/benchmark-{dark,light}.svg. Percentages are computed from the
confusion counts, never from the artifact's pre-rounded ratios.

Usage:  python3 scripts/render_readme_figures.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "benchmarks/results/bench-v1.json"
OUT = ROOT / "docs/assets/readme"

THEMES = {
    "dark": {
        "bg": "#0d1117",
        "text": "#e6edf3",
        "muted": "#8b949e",
        "line": "#30363d",
        "base": "#6e7681",
        "nexora": "#a58bf5",
        "cost": "#e3b341",
    },
    "light": {
        "bg": "#ffffff",
        "text": "#1f2328",
        "muted": "#59636e",
        "line": "#d1d9e0",
        "base": "#9198a1",
        "nexora": "#6447d8",
        "cost": "#9a6700",
    },
}
FONT = "-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans',Helvetica,Arial,sans-serif"


def share(num: int, den: int) -> float:
    return round(num / den * 1000) / 10


def fmt(v: float, unit: str) -> str:
    return f"{v:.1f}{unit}"


def rows(holdout: dict) -> list[dict]:
    nx, rl = holdout["nexora_v2"], holdout["B1_rules"]

    def legit(m: dict) -> tuple[float, str]:
        s = m["scenario"]
        return share(s["fp"], s["fp"] + s["tn"]), f"{s['fp']} of {s['fp'] + s['tn']}"

    def recall(m: dict) -> tuple[float, str]:
        s = m["scenario"]
        return share(s["tp"], s["tp"] + s["fn"]), f"{s['tp']} of {s['tp'] + s['fn']}"

    return [
        {
            "title": "Alerts per dataset",
            "hint": "lower is better",
            "max": 45,
            "unit": "",
            "rules": (rl["alerts"]["per_dataset"], ""),
            "nexora": (nx["alerts"]["per_dataset"], ""),
        },
        {
            "title": "Legitimate networks flagged",
            "hint": "lower is better",
            "max": 100,
            "unit": " %",
            "rules": legit(rl),
            "nexora": legit(nx),
        },
        {
            "title": "Suspicious networks found (recall)",
            "hint": "higher is better",
            "max": 100,
            "unit": " %",
            "rules": recall(rl),
            "nexora": recall(nx),
            "cost": True,
        },
    ]


def svg(theme: str, data: list[dict], datasets: int, commit: str) -> str:
    c = THEMES[theme]
    w, x0, bar_w, row_h = 880, 150, 470, 128
    h = 70 + row_h * len(data) + 34
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'font-family="{FONT}" role="img" aria-label="NEXORA vs per-account monitoring rules, bench-v1 holdout">',
        f'<rect width="{w}" height="{h}" rx="12" fill="{c["bg"]}"/>',
        f'<rect x="24" y="26" width="12" height="12" rx="3" fill="{c["base"]}"/>'
        f'<text x="44" y="37" font-size="14" fill="{c["muted"]}">Per-account monitoring rules (B1)</text>',
        f'<rect x="290" y="26" width="12" height="12" rx="3" fill="{c["nexora"]}"/>'
        f'<text x="310" y="37" font-size="14" fill="{c["muted"]}">NEXORA (risk-policy-v2)</text>',
    ]
    y = 70
    for r in data:
        out.append(f'<line x1="24" x2="{w - 24}" y1="{y}" y2="{y}" stroke="{c["line"]}"/>')
        out.append(
            f'<text x="24" y="{y + 30}" font-size="17" font-weight="600" fill="{c["text"]}">{r["title"]}'
            f'<tspan dx="10" font-size="13" font-weight="400" fill="{c["muted"]}">{r["hint"]}</tspan></text>'
        )
        if r.get("cost"):
            delta = r["rules"][0] - r["nexora"][0]
            out.append(
                f'<text x="{w - 24}" y="{y + 30}" font-size="14" font-weight="600" text-anchor="end" '
                f'fill="{c["cost"]}">−{delta:.1f} pp: the cost of a shorter queue</text>'
            )
        for i, key in enumerate(("rules", "nexora")):
            v, sub = r[key]
            by = y + 50 + i * 34
            colour = c["base"] if key == "rules" else (c["cost"] if r.get("cost") else c["nexora"])
            label = "Rules" if key == "rules" else "NEXORA"
            out.append(f'<text x="24" y="{by + 13}" font-size="14" fill="{c["muted"]}">{label}</text>')
            width = bar_w * v / r["max"]
            out.append(f'<rect x="{x0}" y="{by}" width="{width:.1f}" height="18" rx="3" fill="{colour}"/>')
            out.append(
                f'<text x="{x0 + bar_w + 92}" y="{by + 15}" font-size="18" font-weight="650" text-anchor="end" '
                f'fill="{c["text"] if key == "nexora" else c["muted"]}">{fmt(v, r["unit"])}</text>'
            )
            if sub:
                sx = x0 + bar_w + 108
                out.append(f'<text x="{sx}" y="{by + 14}" font-size="13" fill="{c["muted"]}">{sub}</text>')
        y += row_h
    out.append(
        f'<text x="24" y="{h - 16}" font-size="12" fill="{c["muted"]}">bench-v1 holdout · {datasets} synthetic '
        f"datasets · 220 planted networks · commit {commit} · not a result on bank data</text>"
    )
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main() -> None:
    d = json.loads(SRC.read_text())
    data = rows(d["results"]["holdout"])
    OUT.mkdir(parents=True, exist_ok=True)
    for theme in THEMES:
        path = OUT / f"benchmark-{theme}.svg"
        path.write_text(svg(theme, data, d["splits"]["holdout"]["datasets"], d["code"]["commit"][:7]))
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
