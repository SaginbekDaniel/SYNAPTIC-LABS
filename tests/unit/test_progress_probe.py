"""Regression tests for ``docs/handoff/probes/progress.py``.

The completion figure is computed from the backlog, never typed. These tests pin the formula and the
evidence rule: a DONE claim without a reachable commit and an existing ledger entry is a problem, so the
percentage cannot run ahead of the evidence.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
PROBE = ROOT / "docs" / "handoff" / "probes" / "progress.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("progress_probe", PROBE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


progress = _load()

BACKLOG = """\
* **Critical path** (release): B-001, B-003.

### B-001 · P0 · Something critical
* **Status**: DONE · commit `abc1234` · L-0001
* **Depends on**: none.

### B-002 · P1 · Something gated · human-gated
* **Status**: BLOCKED · waiting on the owner

### B-003 · P2 · Something ordinary
* **Status**: TODO

### B-004 · P3 · optional · Something small
* **Status**: VERIFIED
"""
LEDGER = "### L-0001 · 2026-11-25 · B-001 · status: done\n"


def test_weighted_formula_and_critical_path() -> None:
    tasks, critical, problems = progress.parse_backlog(BACKLOG)
    assert problems == []
    assert critical == {"B-001", "B-003"}
    s = progress.summarise(tasks, critical)
    # weights 8 + 5 + 3 + 1 = 17; only the P0 is DONE
    assert s["verified_completion"] == round(100 * 8 / 17, 1)
    assert s["critical_progress"] == round(100 * 8 / 11, 1)
    assert s["blocked"] == ["B-002"]
    assert s["in_progress"] == ["B-004"]
    assert s["release_blocking_open"] == []
    assert s["done"] == 1 and s["remaining"] == 3


def test_verified_is_not_done() -> None:
    tasks, critical, _ = progress.parse_backlog(BACKLOG.replace("TODO", "VERIFIED"))
    assert progress.summarise(tasks, critical)["done"] == 1


def test_done_requires_reachable_commit_and_ledger_entry() -> None:
    tasks, _, _ = progress.parse_backlog(BACKLOG)
    assert progress.check_evidence(tasks, LEDGER, reachable=lambda _sha: True) == []
    missing_entry = progress.check_evidence(tasks, "", reachable=lambda _sha: True)
    assert any("L-0001 does not exist" in p for p in missing_entry)
    unreachable = progress.check_evidence(tasks, LEDGER, reachable=lambda _sha: False)
    assert any("not reachable" in p for p in unreachable)


def test_done_without_evidence_is_rejected() -> None:
    tasks, _, _ = progress.parse_backlog(BACKLOG.replace("DONE · commit `abc1234` · L-0001", "DONE"))
    problems = progress.check_evidence(tasks, LEDGER, reachable=lambda _sha: True)
    assert any("DONE must read" in p for p in problems)


def test_missing_duplicate_and_unknown_status_lines_are_problems() -> None:
    no_status = BACKLOG.replace("* **Status**: TODO\n", "")
    assert any("B-003: expected exactly one" in p for p in progress.parse_backlog(no_status)[2])
    twice = BACKLOG.replace("* **Status**: TODO\n", "* **Status**: TODO\n* **Status**: TODO\n")
    assert any("found 2" in p for p in progress.parse_backlog(twice)[2])
    unknown = BACKLOG.replace("Status**: TODO", "Status**: ALMOST")
    assert any("unknown status 'ALMOST'" in p for p in progress.parse_backlog(unknown)[2])
    no_critical = BACKLOG.replace("* **Critical path** (release): B-001, B-003.\n", "")
    assert any("no **Critical path**" in p for p in progress.parse_backlog(no_critical)[2])


def test_repository_backlog_is_consistent() -> None:
    """The real documents parse, every task has a status and every DONE claim has its evidence."""
    proc = subprocess.run([sys.executable, str(PROBE)], cwd=ROOT, capture_output=True, text=True, check=False)
    assert proc.returncode == 0, proc.stderr
    assert "Verified completion" in proc.stdout


def test_dependency_map_diagram_is_generated_not_hand_edited() -> None:
    """DEPENDENCY_MAP.md embeds exactly what ``progress.py --mermaid`` produces from the backlog."""
    doc = (ROOT / "docs" / "handoff" / "DEPENDENCY_MAP.md").read_text(encoding="utf-8")
    start, end = "<!-- generated:mermaid:start -->\n```mermaid\n", "\n```\n<!-- generated:mermaid:end -->"
    assert start in doc and end in doc
    embedded = doc.split(start, 1)[1].split(end, 1)[0]
    text = progress.BACKLOG.read_text(encoding="utf-8")
    tasks, critical, _ = progress.parse_backlog(text)
    assert embedded == progress.mermaid(tasks, critical, progress.dependencies(text)), (
        "regenerate with: python3 docs/handoff/probes/progress.py --mermaid"
    )


def test_mermaid_edges_follow_depends_on_lines() -> None:
    deps = progress.dependencies(
        BACKLOG.replace("* **Status**: TODO\n", "* **Status**: TODO\n* **Depends on**: B-001, B-002.\n")
    )
    assert deps["B-003"] == {"B-001", "B-002"}
    tasks, critical, _ = progress.parse_backlog(BACKLOG)
    graph = progress.mermaid(tasks, critical, deps)
    assert "B001 --> B003" in graph and "B002 --> B003" in graph
    assert "class B001,B003 critical" in graph
