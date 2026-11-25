"""Turn the dependency-audit allow-list into ``pip-audit`` arguments, refusing stale or unexplained entries.

Usage (CI, .github/workflows/audit.yml):  python3 scripts/audit_allowlist.py .github/pip-audit-allowlist.txt

File format, one entry per line (``#`` starts a comment)::

    <advisory id>  <expiry YYYY-MM-DD>  <reason: why it cannot be fixed yet and what will fix it>

Prints ``--ignore-vuln <id>`` for every valid entry. Exits 1 - so the audit fails closed - when an entry is
malformed, has no reason, or has expired: an exception must be re-justified, never silently kept.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

LINE_RE = re.compile(r"^(?P<id>[A-Za-z][A-Za-z0-9._:-]+)\s+(?P<expiry>\d{4}-\d{2}-\d{2})\s+(?P<reason>\S.*)$")


@dataclass(frozen=True)
class Entry:
    advisory: str
    expiry: date
    reason: str


def parse(text: str, today: date) -> tuple[list[Entry], list[str]]:
    entries: list[Entry] = []
    problems: list[str] = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        m = LINE_RE.match(line)
        if not m:
            problems.append(f"line {n}: expected '<id> <YYYY-MM-DD> <reason>', got {line!r}")
            continue
        try:
            expiry = date.fromisoformat(m["expiry"])
        except ValueError:
            problems.append(f"line {n}: invalid date {m['expiry']!r}")
            continue
        if expiry < today:
            problems.append(f"line {n}: {m['id']} expired on {expiry.isoformat()} - fix the dependency or re-justify")
            continue
        entries.append(Entry(m["id"], expiry, m["reason"].strip()))
    return entries, problems


def main(argv: list[str], today: date | None = None) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    entries, problems = parse(Path(argv[0]).read_text(encoding="utf-8"), today or date.today())
    for p in problems:
        print(f"audit allow-list: {p}", file=sys.stderr)
    if problems:
        return 1
    print(" ".join(f"--ignore-vuln {e.advisory}" for e in entries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
