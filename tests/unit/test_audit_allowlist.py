"""The dependency-audit allow-list fails closed (backlog B-014): no stale, malformed or unexplained exception."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from scripts import audit_allowlist as al

TODAY = date(2026, 11, 25)
ROOT = Path(__file__).resolve().parents[2]


def test_valid_entries_become_ignore_arguments(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "allow.txt"
    f.write_text(
        "# comment\n\nGHSA-aaaa-bbbb-cccc 2026-12-31  no fixed release yet; tracked upstream\n"
        "PYSEC-2026-1 2026-11-25 fixed by the next minor  # trailing comment\n",
        encoding="utf-8",
    )
    assert al.main([str(f)], today=TODAY) == 0
    assert capsys.readouterr().out.strip() == "--ignore-vuln GHSA-aaaa-bbbb-cccc --ignore-vuln PYSEC-2026-1"


def test_expired_entry_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    f = tmp_path / "allow.txt"
    f.write_text("GHSA-aaaa-bbbb-cccc 2026-11-24 was waiting for a release\n", encoding="utf-8")
    assert al.main([str(f)], today=TODAY) == 1
    assert "expired on 2026-11-24" in capsys.readouterr().err


def test_entry_without_reason_or_date_fails() -> None:
    entries, problems = al.parse("GHSA-aaaa-bbbb-cccc 2026-12-31\nPYSEC-1 soon because reasons\n", TODAY)
    assert entries == [] and len(problems) == 2


def test_invalid_calendar_date_fails() -> None:
    _, problems = al.parse("GHSA-aaaa-bbbb-cccc 2026-02-30 reason\n", TODAY)
    assert problems and "invalid date" in problems[0]


def test_committed_allow_list_is_valid_today() -> None:
    """The repository's own list parses and holds no expired entry."""
    text = (ROOT / ".github" / "pip-audit-allowlist.txt").read_text(encoding="utf-8")
    entries, problems = al.parse(text, date.today())
    assert problems == []
    assert all(e.reason for e in entries)
