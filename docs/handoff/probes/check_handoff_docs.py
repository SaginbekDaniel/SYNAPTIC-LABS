"""Mechanical consistency check for docs/handoff/*.md.

Run from the repository root:  python3 docs/handoff/probes/check_handoff_docs.py
Checks: referenced repository paths and markdown links exist, branches exist on origin, commit SHAs are
reachable from HEAD or an origin branch, npm/make commands exist, every H-nn is defined in the master
handoff, backlog waves/dependencies are consistent and acyclic. Exit code 1 on any problem.
It cannot judge whether a *claim* is true - only that what the documents point at is real.

The result must not depend on the machine it runs on, so it validates against the shared repository,
not the local working state:

* **Paths** inside code spans, fenced blocks and link targets are always checked. In prose a token is a
  path only if it is unambiguous - more than one segment below the top-level directory, a file extension,
  or a trailing slash. A bare ``docs/test`` in a sentence is the "a/b" idiom ("the docs/test commit"),
  not a reference; write a path in backticks to have it checked.
* A path followed by ``(new`` is exempt (it does not exist yet). A path that git ignores is build output
  (for example the MediaPipe assets ``vite build`` writes): it exists only on machines that built, so it
  is counted as generated and not checked.
* **Commits** must be reachable from HEAD or an origin branch; a SHA that exists only in one container's
  object store is invisible to the next session. A commit deliberately never published is written as
  ``local commit `<sha>` `` and is not looked up.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HANDOFF = ROOT / "docs" / "handoff"

PATH_RE = re.compile(
    r"(?<![\w/.-])((?:scripts|docs|apps|src|tests|migrations|configs|benchmarks|\.github|\.railway)/[\w./@-]*[\w/])"
)
FENCE_RE = re.compile(r"^```.*?^```", re.S | re.M)
CODE_RE = re.compile(r"`[^`\n]+`")
LINK_TARGET_RE = re.compile(r"\]\([^)\s]+\)")
LINK_RE = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
BRANCH_RE = re.compile(r"(?:origin/)?(claude/[\w-]+|graph-workspace-wip)")
SHA_RE = re.compile(r"`([0-9a-f]{7,40})`")
LOCAL_COMMIT_MARK = "local commit "


def default_docs() -> list[Path]:
    return [*sorted(HANDOFF.glob("*.md")), ROOT / "docs" / "implementation" / "GRAPH_GESTURE_VERIFICATION.md"]


def git(*args: str, root: Path = ROOT) -> tuple[int, str]:
    p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True)
    return p.returncode, p.stdout.strip()


# ---- 1. paths --------------------------------------------------------------------------------
def code_spans(text: str) -> list[tuple[int, int]]:
    """Character ranges of fenced blocks, inline code and markdown link targets."""
    return [m.span() for rx in (FENCE_RE, CODE_RE, LINK_TARGET_RE) for m in rx.finditer(text)]


def unambiguous_in_prose(token: str) -> bool:
    below_top = token.split("/", 1)[1]
    last = below_top.rstrip("/").rsplit("/", 1)[-1]
    return token.endswith("/") or "/" in below_top.rstrip("/") or re.search(r"\.\w+$", last) is not None


def path_references(text: str) -> list[str]:
    """Repository paths the text refers to (exempt and ambiguous tokens removed)."""
    spans = code_spans(text)
    refs: list[str] = []
    for m in PATH_RE.finditer(text):
        token = m.group(1).rstrip(".")
        tail = text[m.end() : m.end() + 24]
        if "(new" in tail or any(c in token for c in "*<>{}") or token.endswith(("..", "...")):
            continue  # "x/y/{a,b}", globs and "path/…" prose
        in_code = any(a <= m.start() < b for a, b in spans)
        if not in_code and not unambiguous_in_prose(token):
            continue
        refs.append(token)
    return refs


def is_generated(path: str, root: Path = ROOT) -> bool:
    """True when git ignores the path: build output that exists only where someone built."""
    return git("check-ignore", "-q", path, root=root)[0] == 0


def check_paths(docs: Iterable[Path], root: Path = ROOT) -> tuple[list[str], int, int]:
    problems: list[str] = []
    checked = generated = 0
    for doc in docs:
        for token in path_references(doc.read_text()):
            if is_generated(token, root):
                generated += 1
                continue
            checked += 1
            if not (root / token).exists():
                problems.append(f"{doc.name}: path does not exist: {token}")
    return problems, checked, generated


# ---- 3. commits ------------------------------------------------------------------------------
def sha_references(text: str) -> list[tuple[str, bool]]:
    """(sha, declared_local) for every backticked SHA; declared_local = written as `local commit <sha>`."""
    out: list[tuple[str, bool]] = []
    for m in SHA_RE.finditer(text):
        sha = m.group(1)
        if sha.isdigit():
            continue
        out.append((sha, text[: m.start()].endswith(LOCAL_COMMIT_MARK)))
    return out


def reachable_commits(root: Path = ROOT) -> set[str]:
    return set(git("rev-list", "HEAD", "--remotes=origin", root=root)[1].split())


def check_commits(name: str, text: str, reachable: set[str], root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for sha, declared_local in sorted(set(sha_references(text))):
        if declared_local:
            continue
        code, full = git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}", root=root)
        if code != 0:
            problems.append(f"{name}: commit not found: {sha}")
        elif full not in reachable:
            problems.append(f"{name}: commit {sha} exists only locally (not reachable from HEAD or origin)")
    return problems


def main() -> int:
    docs = default_docs()
    problems, checked_paths, generated_paths = check_paths(docs)

    # a pathspec that is wrong for the working directory makes `git diff --exit-code` pass silently
    for doc in docs:
        if "-- openapi.json apps/web/" in doc.read_text():
            problems.append(f"{doc.name}: OpenAPI drift check would pass vacuously (apps/web/ prefix inside apps/web)")

    # ---- 2. markdown links --------------------------------------------------------------------
    for doc in docs:
        for target in LINK_RE.findall(doc.read_text()):
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            rel = target.split("#")[0]
            if rel and not (doc.parent / rel).resolve().exists():
                problems.append(f"{doc.name}: broken link: {target}")

    # ---- 3. branches and commits --------------------------------------------------------------
    reachable = reachable_commits()
    for doc in docs:
        text = doc.read_text()
        for b in sorted(set(BRANCH_RE.findall(text))):
            if git("rev-parse", "--verify", "--quiet", f"origin/{b}")[0] != 0:
                problems.append(f"{doc.name}: branch not found on origin: {b}")
        problems += check_commits(doc.name, text, reachable)
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
            problems.append(f"branch not found on origin: claude/{short}")

    # ---- 4. commands --------------------------------------------------------------------------
    scripts: set[str] = set()
    for pkg in ("apps/web", "apps/pitch", ".railway"):
        scripts |= set(json.loads((ROOT / pkg / "package.json").read_text()).get("scripts", {}))
    makefile = (ROOT / "Makefile").read_text()
    targets = set(re.findall(r"^([a-z-]+):", makefile, re.M))
    for doc in docs:
        text = doc.read_text()
        for name in re.findall(r"npm run ([\w:-]+)", text):
            if name not in scripts:
                problems.append(f"{doc.name}: unknown npm script: {name}")
        for name in re.findall(r"\bmake ([a-z-]+)", text):
            if name not in targets:
                problems.append(f"{doc.name}: unknown make target: {name}")

    # ---- 5. findings referenced vs defined ----------------------------------------------------
    master = (HANDOFF / "MASTER_HANDOFF.md").read_text()
    defined = set(re.findall(r"\*\*(H-\d\d)\b", master)) | set(re.findall(r"^\| (H-\d\d) \|", master, re.M))
    for doc in docs:
        for h in sorted(set(re.findall(r"\bH-\d\d\b", doc.read_text()))):
            if h not in defined:
                problems.append(f"{doc.name}: finding {h} is not defined in MASTER_HANDOFF §16")
    tasks_defined = set(re.findall(r"^### (B-\d{3}) ·", (HANDOFF / "EXECUTION_BACKLOG.md").read_text(), re.M))
    for doc in docs:
        for b in sorted(set(re.findall(r"\bB-\d{3}\b", doc.read_text()))):
            if b not in tasks_defined:
                problems.append(f"{doc.name}: task {b} is not defined in EXECUTION_BACKLOG")

    # ---- 6. backlog structure -----------------------------------------------------------------
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
                problems.append(f"{tid}: missing field {field}")
        m = re.search(r"\*\*Depends on\*\*: (.*?)\n\* \*\*", body, re.S)
        if not m:
            problems.append(f"{tid}: cannot parse Depends on")
            continue
        head = re.split(r"[(.]", m.group(1))[0]  # ids before the first parenthesis or full stop
        deps[tid] = set(re.findall(r"B-\d{3}", head))
    for tid, ds in deps.items():
        for d in ds:
            if d not in deps:
                problems.append(f"{tid}: depends on unknown task {d}")
    # acyclic
    state: dict[str, int] = {}

    def visit(t: str, path: list[str]) -> None:
        if state.get(t) == 1:
            problems.append("dependency cycle: " + " -> ".join([*path, t]))
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
        problems.append("backlog: cannot find the edges paragraph")
    else:
        for src, dsts in re.findall(r"(B-\d{3})→((?:B-\d{3})(?:,\s*B-\d{3})*)", para.group(1)):
            edges[src] = set(re.findall(r"B-\d{3}", dsts))
        for t, ds in deps.items():
            if ds != edges.get(t, set()):
                problems.append(
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
        problems.append(f"wave table mismatch: missing={missing} unknown={extra} duplicated={dup}")

    print(
        f"checked {checked_paths} paths ({generated_paths} git-ignored, not checked), {len(deps)} tasks, "
        f"{len(defined)} findings, {len(docs)} documents"
    )
    if problems:
        print(f"{len(problems)} PROBLEM(S):")
        for p in problems:
            print("  -", p)
        return 1
    print("OK: no problems found")
    return 0


if __name__ == "__main__":
    sys.exit(main())
