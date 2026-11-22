"""Mechanical consistency check for docs/handoff/*.md.

Run from the repository root:  python3 docs/handoff/probes/check_handoff_docs.py
Checks: referenced repository paths and markdown links exist (a path followed by "(new" is exempt),
branches and commit SHAs exist in git, npm/make commands exist, every H-nn is defined in the master
handoff, backlog waves/dependencies are consistent and acyclic. Exit code 1 on any problem.
It cannot judge whether a *claim* is true - only that what the documents point at is real.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / "docs" / "handoff"
DOCS = [*sorted(HANDOFF.glob("*.md")), ROOT / "docs" / "implementation" / "GRAPH_GESTURE_VERIFICATION.md"]
problems: list[str] = []


def git(*args: str) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


def fail(msg: str) -> None:
    problems.append(msg)


# ---- 1. paths --------------------------------------------------------------------------------
PATH_RE = re.compile(
    r"(?<![\w/.-])((?:scripts|docs|apps|src|tests|migrations|configs|benchmarks|\.github|\.railway)/[\w./@-]*[\w/])"
)
checked_paths = 0
for doc in DOCS:
    text = doc.read_text()
    for m in PATH_RE.finditer(text):
        token = m.group(1).rstrip(".")
        tail = text[m.end() : m.end() + 24]
        if "(new" in tail or any(c in token for c in "*<>{}") or token.endswith(("..", "...")):
            continue
        # "x/y/{a,b}" style and "path/…" prose are skipped above; everything else must exist
        checked_paths += 1
        if not (ROOT / token).exists():
            fail(f"{doc.name}: path does not exist: {token}")

# a pathspec that is wrong for the working directory makes `git diff --exit-code` pass silently
for doc in DOCS:
    if "-- openapi.json apps/web/" in doc.read_text():
        fail(f"{doc.name}: OpenAPI drift check would pass vacuously (apps/web/ prefix inside apps/web)")

# ---- 2. markdown links ------------------------------------------------------------------------
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
for doc in DOCS:
    for target in LINK_RE.findall(doc.read_text()):
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        rel = target.split("#")[0]
        if rel and not (doc.parent / rel).resolve().exists():
            fail(f"{doc.name}: broken link: {target}")

# ---- 3. branches and commits ---------------------------------------------------------------------
BRANCH_RE = re.compile(r"(?:origin/)?(claude/[\w-]+|graph-workspace-wip)")
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
for doc in DOCS:
    text = doc.read_text()
    for b in sorted(set(BRANCH_RE.findall(text))):
        if git("rev-parse", "--verify", "--quiet", f"origin/{b}")[0] != 0:
            fail(f"{doc.name}: branch not found on origin: {b}")
    for sha in sorted(set(SHA_RE.findall(text))):
        if sha.isdigit():
            continue
        if git("cat-file", "-e", f"{sha}^{{commit}}")[0] != 0:
            fail(f"{doc.name}: commit not found: {sha}")
# short branch names used in tables without the claude/ prefix
for short in (
    "eloquent-planck-pwnbd8",
    "sharp-cannon-xkrybs",
    "admiring-fermat-9fc4nx",
    "great-lovelace-0gmpmi",
    "peaceful-babbage-cyqrox",
    "stoic-dijkstra-y9o5bm",
    "quirky-ride-v565zk",
    "kind-lamport-uym9zx",
):
    if git("rev-parse", "--verify", "--quiet", f"origin/claude/{short}")[0] != 0:
        fail(f"branch not found on origin: claude/{short}")

# ---- 4. commands ---------------------------------------------------------------------------------
scripts: set[str] = set()
for pkg in ("apps/web", "apps/pitch", ".railway"):
    scripts |= set(json.loads((ROOT / pkg / "package.json").read_text()).get("scripts", {}))
makefile = (ROOT / "Makefile").read_text()
targets = set(re.findall(r"^([a-z-]+):", makefile, re.M))
for doc in DOCS:
    text = doc.read_text()
    for name in re.findall(r"npm run ([\w:-]+)", text):
        if name not in scripts:
            fail(f"{doc.name}: unknown npm script: {name}")
    for name in re.findall(r"\bmake ([a-z-]+)", text):
        if name not in targets:
            fail(f"{doc.name}: unknown make target: {name}")

# ---- 5. findings referenced vs defined -----------------------------------------------------------------
master = (HANDOFF / "MASTER_HANDOFF.md").read_text()
defined = set(re.findall(r"\*\*(H-\d\d)\b", master)) | set(re.findall(r"^\| (H-\d\d) \|", master, re.M))
for doc in DOCS:
    for h in sorted(set(re.findall(r"\bH-\d\d\b", doc.read_text()))):
        if h not in defined:
            fail(f"{doc.name}: finding {h} is not defined in MASTER_HANDOFF §16")
tasks_defined = set(re.findall(r"^### (B-\d{3}) ·", (HANDOFF / "EXECUTION_BACKLOG.md").read_text(), re.M))
for doc in DOCS:
    for b in sorted(set(re.findall(r"\bB-\d{3}\b", doc.read_text()))):
        if b not in tasks_defined:
            fail(f"{doc.name}: task {b} is not defined in EXECUTION_BACKLOG")

# ---- 6. backlog structure ------------------------------------------------------------------------------
backlog = (HANDOFF / "EXECUTION_BACKLOG.md").read_text()
sections = re.split(r"^### (B-\d{3}) ·", backlog, flags=re.M)
deps: dict[str, set[str]] = {}
required = (
    "**Rationale**",
    "**Modules**",
    "**Depends on**",
    "**Implementation**",
    "**Acceptance**",
    "**Tests**",
    "**Expected improvement**",
    "**Risk / rollback**",
)
for i in range(1, len(sections), 2):
    tid, body = sections[i], sections[i + 1]
    for field in required:
        if field not in body:
            fail(f"{tid}: missing field {field}")
    m = re.search(r"\*\*Depends on\*\*: (.*?)\n\* \*\*", body, re.S)
    if not m:
        fail(f"{tid}: cannot parse Depends on")
        continue
    head = re.split(r"[(.]", m.group(1))[0]  # ids before the first parenthesis or full stop
    deps[tid] = set(re.findall(r"B-\d{3}", head))
for tid, ds in deps.items():
    for d in ds:
        if d not in deps:
            fail(f"{tid}: depends on unknown task {d}")
# acyclic
state: dict[str, int] = {}


def visit(t: str, path: list[str]) -> None:
    if state.get(t) == 1:
        fail("dependency cycle: " + " -> ".join([*path, t]))
        return
    if state.get(t) == 2:
        return
    state[t] = 1
    for d in deps.get(t, ()):
        visit(d, [*path, t])
    state[t] = 2


for t in deps:
    visit(t, [])
# the "Edges" paragraph must equal the per-task Depends on lines
edges: dict[str, set[str]] = {}
para = re.search(r"Edges \(task → prerequisites\):(.*?)The graph is acyclic", backlog, re.S)
if not para:
    fail("backlog: cannot find the edges paragraph")
else:
    for src, dsts in re.findall(r"(B-\d{3})→((?:B-\d{3})(?:,\s*B-\d{3})*)", para.group(1)):
        edges[src] = set(re.findall(r"B-\d{3}", dsts))
    for t, ds in deps.items():
        if ds != edges.get(t, set()):
            fail(
                f"edges paragraph disagrees with {t}: tasks say {sorted(ds)}, "
                f"paragraph says {sorted(edges.get(t, set()))}"
            )
# every task appears exactly once in the wave table
wave_rows = re.findall(r"^\| (\d) \| [^|]+ \| ([^|]+) \|", backlog, re.M)
listed = [b for _, cell in wave_rows for b in re.findall(r"B-\d{3}", cell)]
if sorted(listed) != sorted(deps):
    missing = sorted(set(deps) - set(listed))
    extra = sorted(set(listed) - set(deps))
    dup = sorted({b for b in listed if listed.count(b) > 1})
    fail(f"wave table mismatch: missing={missing} unknown={extra} duplicated={dup}")

print(f"checked {checked_paths} paths, {len(deps)} tasks, {len(defined)} findings, {len(DOCS)} documents")
if problems:
    print(f"{len(problems)} PROBLEM(S):")
    for p in problems:
        print("  -", p)
    sys.exit(1)
print("OK: no problems found")
