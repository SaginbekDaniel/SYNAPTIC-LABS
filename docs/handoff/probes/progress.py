"""Computed completion progress for the execution backlog.

Run from the repository root:  python3 docs/handoff/probes/progress.py [--markdown | --mermaid]

The numbers are derived only from ``docs/handoff/EXECUTION_BACKLOG.md`` (one ``* **Status**:`` line per task,
the ``**Critical path**`` convention line) and ``docs/handoff/EXECUTION_LEDGER.md``. Nobody types a percentage:

    verified completion = sum(weight of DONE tasks) / sum(weight of all tasks) x 100
    weights: P0 = 8, P1 = 5, P2 = 3, P3 = 1  (fixed; never tune them to move the figure)

A task counts as DONE only when its status line names a commit reachable from HEAD or an origin branch and a
ledger entry that exists. Anything else (TODO, IN_PROGRESS, BLOCKED, IMPLEMENTED, VERIFIED) counts as not done.
Exit code 1 when a status line is missing or malformed, or when a DONE claim lacks its evidence - so the
figure cannot drift from the documents. 100 % here does not replace the release gates in RELEASE_CHECKLIST.md.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BACKLOG = ROOT / "docs" / "handoff" / "EXECUTION_BACKLOG.md"
LEDGER = ROOT / "docs" / "handoff" / "EXECUTION_LEDGER.md"

WEIGHTS = {"P0": 8, "P1": 5, "P2": 3, "P3": 1}
STATUSES = ("TODO", "IN_PROGRESS", "BLOCKED", "IMPLEMENTED", "VERIFIED", "DONE")

HEADING_RE = re.compile(r"^### (B-\d{3}) · (P[0-3])\b[^\n]*$", re.M)
STATUS_RE = re.compile(r"^\* \*\*Status\*\*: ([A-Z_]+)(.*)$", re.M)
DONE_RE = re.compile(r"^· commit `([0-9a-f]{7,40})` · (L-\d{4})$")
CRITICAL_RE = re.compile(r"\*\*Critical path\*\*[^:]*:\s*((?:B-\d{3}[,.\s]*)+)")


@dataclass(frozen=True)
class Task:
    tid: str
    priority: str
    status: str
    detail: str
    gated: bool

    @property
    def weight(self) -> int:
        return WEIGHTS[self.priority]


def parse_backlog(text: str) -> tuple[list[Task], set[str], list[str]]:
    """Return the tasks, the critical-path ids and the problems found while parsing."""
    problems: list[str] = []
    heads = list(HEADING_RE.finditer(text))
    tasks: list[Task] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        body = text[m.end() : end]
        statuses = STATUS_RE.findall(body)
        if len(statuses) != 1:
            problems.append(f"{m.group(1)}: expected exactly one Status line, found {len(statuses)}")
            continue
        status, detail = statuses[0]
        if status not in STATUSES:
            problems.append(f"{m.group(1)}: unknown status {status!r}")
            continue
        gated = "human-gated" in m.group(0) or "requires decision" in m.group(0) or "approval" in m.group(0)
        tasks.append(Task(m.group(1), m.group(2), status, detail.strip(), gated))
    cm = CRITICAL_RE.search(text)
    critical = set(re.findall(r"B-\d{3}", cm.group(1))) if cm else set()
    if not cm:
        problems.append("backlog: no **Critical path** line")
    unknown = critical - {t.tid for t in tasks}
    if unknown:
        problems.append(f"critical path names unknown tasks: {sorted(unknown)}")
    return tasks, critical, problems


def _reachable(sha: str) -> bool:
    """True when ``sha`` is an ancestor of HEAD or contained in an origin branch (not just a local object)."""
    git = ["git", "-C", str(ROOT)]
    ancestor = subprocess.run([*git, "merge-base", "--is-ancestor", sha, "HEAD"], capture_output=True, check=False)
    if ancestor.returncode == 0:
        return True
    proc = subprocess.run([*git, "branch", "-r", "--contains", sha], capture_output=True, text=True, check=False)
    return proc.returncode == 0 and "origin/" in proc.stdout


def check_evidence(tasks: list[Task], ledger_text: str, reachable: Callable[[str], bool] = _reachable) -> list[str]:
    """Every DONE task must cite a reachable commit and an existing ledger entry."""
    problems: list[str] = []
    entries = set(re.findall(r"^### (L-\d{4}) ", ledger_text, re.M))
    for t in tasks:
        if t.status != "DONE":
            continue
        m = DONE_RE.match(t.detail)
        if not m:
            problems.append(f"{t.tid}: DONE must read 'DONE · commit `<sha>` · L-nnnn', got {t.detail!r}")
            continue
        sha, entry = m.groups()
        if entry not in entries:
            problems.append(f"{t.tid}: ledger entry {entry} does not exist")
        if not reachable(sha):
            problems.append(f"{t.tid}: commit {sha} is not reachable from HEAD or an origin branch")
    return problems


def _pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def summarise(tasks: list[Task], critical: set[str]) -> dict[str, object]:
    done = [t for t in tasks if t.status == "DONE"]
    crit = [t for t in tasks if t.tid in critical]
    by_priority = {}
    for p in WEIGHTS:
        in_p = [t for t in tasks if t.priority == p]
        by_priority[p] = (sum(1 for t in in_p if t.status == "DONE"), len(in_p))
    return {
        "verified_completion": _pct(sum(t.weight for t in done), sum(t.weight for t in tasks)),
        "total": len(tasks),
        "done": len(done),
        "remaining": len(tasks) - len(done),
        "blocked": sorted(t.tid for t in tasks if t.status == "BLOCKED"),
        "in_progress": sorted(t.tid for t in tasks if t.status in {"IN_PROGRESS", "IMPLEMENTED", "VERIFIED"}),
        "critical_done": sorted(t.tid for t in crit if t.status == "DONE"),
        "critical_open": sorted(t.tid for t in crit if t.status != "DONE"),
        "critical_progress": _pct(sum(t.weight for t in crit if t.status == "DONE"), sum(t.weight for t in crit)),
        "release_blocking_open": sorted(t.tid for t in tasks if t.priority == "P0" and t.status != "DONE"),
        "by_priority": by_priority,
    }


def render(s: dict[str, object], markdown: bool) -> str:
    bp = s["by_priority"]
    assert isinstance(bp, dict)
    rows = [
        ("Verified completion (weighted)", f"{s['verified_completion']} %"),
        ("Critical-path progress (weighted)", f"{s['critical_progress']} %"),
        ("Tasks: total / done / remaining", f"{s['total']} / {s['done']} / {s['remaining']}"),
        ("Done by priority (P0, P1, P2, P3)", ", ".join(f"{p} {d}/{n}" for p, (d, n) in bp.items())),
        ("Blocked", ", ".join(s["blocked"]) or "none"),  # type: ignore[arg-type]
        ("In progress / implemented / verified", ", ".join(s["in_progress"]) or "none"),  # type: ignore[arg-type]
        ("Critical path still open", ", ".join(s["critical_open"]) or "none"),  # type: ignore[arg-type]
        ("Open P0 tasks (release-blocking)", ", ".join(s["release_blocking_open"]) or "none"),  # type: ignore[arg-type]
    ]
    if markdown:
        return "| Measure | Value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    width = max(len(k) for k, _ in rows)
    return "\n".join(f"{k.ljust(width)}  {v}" for k, v in rows)


def dependencies(text: str) -> dict[str, set[str]]:
    """Task -> prerequisites, read from each task's ``**Depends on**`` line."""
    heads = list(HEADING_RE.finditer(text))
    deps: dict[str, set[str]] = {}
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        dm = re.search(r"^\* \*\*Depends on\*\*: (.*)$", text[m.end() : end], re.M)
        deps[m.group(1)] = set(re.findall(r"B-\d{3}", dm.group(1))) if dm else set()
    return deps


def mermaid(tasks: list[Task], critical: set[str], deps: dict[str, set[str]]) -> str:
    """Deterministic Mermaid graph: prerequisite --> task, one class per status, thick border = critical path."""
    lines = ["flowchart LR"]
    for t in sorted(tasks, key=lambda t: t.tid):
        lines.append(f'  {t.tid.replace("-", "")}["{t.tid} {t.priority}"]:::{t.status.lower()}')
    for tid in sorted(deps):
        for prereq in sorted(deps[tid]):
            lines.append(f"  {prereq.replace('-', '')} --> {tid.replace('-', '')}")
    crit = ",".join(sorted(c.replace("-", "") for c in critical))
    if crit:
        lines.append(f"  class {crit} critical")
    lines += [
        "  classDef done fill:#1f6f43,color:#fff,stroke:#1f6f43",
        "  classDef blocked fill:#8a2b2b,color:#fff,stroke:#8a2b2b",
        "  classDef todo fill:#3a3f4b,color:#fff,stroke:#3a3f4b",
        "  classDef in_progress fill:#7a5a12,color:#fff,stroke:#7a5a12",
        "  classDef implemented fill:#7a5a12,color:#fff,stroke:#7a5a12",
        "  classDef verified fill:#2d5c7a,color:#fff,stroke:#2d5c7a",
        "  classDef critical stroke:#f2c94c,stroke-width:4px",
    ]
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    text = BACKLOG.read_text(encoding="utf-8")
    tasks, critical, problems = parse_backlog(text)
    problems += check_evidence(tasks, LEDGER.read_text(encoding="utf-8"))
    if "--mermaid" in argv:
        print(mermaid(tasks, critical, dependencies(text)))
    else:
        print(render(summarise(tasks, critical), markdown="--markdown" in argv))
    if problems:
        print(f"\n{len(problems)} PROBLEM(S):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
