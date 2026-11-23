"""The Alembic chain stays a single, linear, immutable line (H-01, backlog B-001).

Two branches once each added a *different* revision ``0003`` on top of ``0002``; merged separately they
would have produced two heads and a failing ``alembic upgrade head`` at deploy. Production recorded
``0003`` = the auth migration, so the integration renumbered the hypotheses migration to ``0004``.

The checker reads every file in ``migrations/versions`` itself (Alembic only *warns* about a duplicate
revision id and silently keeps one of them), then cross-checks Alembic's own view of the heads. It is a
plain function so a test can feed it a directory that reproduces the collision.
"""

from __future__ import annotations

import ast
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
VERSIONS = ROOT / "migrations" / "versions"

# Deployed history. Never edit or renumber these files: a database at revision N has run exactly this
# content. Production is at 0003 (the auth migration) per docs/deployment/railway.md. If one of these
# hashes has to change, the change is a new migration instead.
IMMUTABLE: dict[str, tuple[str, str]] = {
    # revision: (sha256 of the file with "\n" line endings, a table the revision creates)
    "0001": ("3ab31f8e4cb7f3bf155193055d83a97fda7aa1647c983afcdeb9b2ed599cea63", "transactions"),
    "0002": ("2735e0d06f6e43eaff0a8b30b2c79278ff445cab7fb994fe4a3a9ef6a25f1d56", ""),
    "0003": ("7023725a392b8ae68289df2301c1f783e0d89d342625812d6ce1324e6e49f192", "users"),
    "0004": ("a702b935427e3159308e81abd2a3f34fb93e293c8758121cd8ee8ad238058ab7", "hypothesis_assessments"),
}


@dataclass(frozen=True)
class Revision:
    path: Path
    revision: str
    down_revision: str | None
    created_tables: frozenset[str]


def _module_constant(tree: ast.Module, name: str) -> object:
    for node in tree.body:
        target = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target, value = node.target, node.value
        if isinstance(target, ast.Name) and target.id == name:
            return ast.literal_eval(value)
    raise ValueError(f"no module-level {name!r}")


def _created_tables(tree: ast.Module) -> frozenset[str]:
    """Table names passed to ``op.create_table`` inside ``upgrade()``."""
    names: set[str] = set()
    for fn in tree.body:
        if not (isinstance(fn, ast.FunctionDef) and fn.name == "upgrade"):
            continue
        for node in ast.walk(fn):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "create_table"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                names.add(node.args[0].value)
    return frozenset(names)


def read_revisions(versions: Path) -> list[Revision]:
    revisions = []
    for path in sorted(versions.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        down = _module_constant(tree, "down_revision")
        if not (down is None or isinstance(down, str)):
            # A tuple is a merge revision: the chain must stay linear.
            raise ValueError(f"{path.name}: down_revision must be one revision or None, got {down!r}")
        rev = _module_constant(tree, "revision")
        if not isinstance(rev, str):
            raise ValueError(f"{path.name}: revision must be a string, got {rev!r}")
        revisions.append(Revision(path, rev, down, _created_tables(tree)))
    return revisions


def chain_problems(versions: Path, immutable: dict[str, tuple[str, str]] | None = None) -> list[str]:
    """Every violation of the migration conventions in ``versions`` (empty list = healthy)."""
    try:
        revisions = read_revisions(versions)
    except (ValueError, SyntaxError) as exc:
        return [str(exc)]
    problems: list[str] = []
    if not revisions:
        return ["no migrations found"]

    by_id: dict[str, list[Revision]] = {}
    for r in revisions:
        by_id.setdefault(r.revision, []).append(r)
        if not r.path.name.startswith(f"{r.revision}_"):
            problems.append(f"{r.path.name}: file name must start with its revision id {r.revision!r}")
        if not (len(r.revision) == 4 and r.revision.isdigit()):
            problems.append(f"{r.path.name}: revision id {r.revision!r} must be four digits (next free number)")
    for rev, owners in by_id.items():
        if len(owners) > 1:
            problems.append(f"revision {rev!r} defined more than once: {', '.join(o.path.name for o in owners)}")

    children: dict[str | None, list[str]] = {}
    for r in revisions:
        children.setdefault(r.down_revision, []).append(r.revision)
        if r.down_revision is not None and r.down_revision not in by_id:
            problems.append(f"{r.path.name}: down_revision {r.down_revision!r} does not exist")
    bases = children.get(None, [])
    if bases != ["0001"]:
        problems.append(f"the chain must have exactly one base, '0001'; found {sorted(bases)}")
    for parent, kids in children.items():
        if parent is not None and len(kids) > 1:
            problems.append(f"revision {parent!r} has {len(kids)} children {sorted(kids)}: the chain must be linear")
    heads = sorted(rev for rev in by_id if rev not in children)
    if len(heads) != 1:
        problems.append(f"expected exactly one head, found {heads}")

    numbered = sorted(r for r in by_id if r.isdigit())
    for expected, rev in enumerate(numbered, start=1):
        if int(rev) != expected:
            problems.append(f"revision ids must be consecutive from 0001; {rev!r} found where {expected:04d} belongs")
            break
        down = by_id[rev][0].down_revision
        want = None if expected == 1 else f"{expected - 1:04d}"
        if len(by_id[rev]) == 1 and down != want:
            problems.append(f"revision {rev!r} must revise {want!r}, not {down!r}")

    for rev, (digest, table) in (IMMUTABLE if immutable is None else immutable).items():
        owners = by_id.get(rev, [])
        if len(owners) != 1:
            problems.append(f"deployed revision {rev!r} must exist exactly once")
            continue
        actual = hashlib.sha256(owners[0].path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
        if digest and actual != digest:
            problems.append(f"{owners[0].path.name}: deployed migration was edited; add a new revision instead")
        if table and table not in owners[0].created_tables:
            problems.append(f"revision {rev!r} must create table {table!r} (production history)")
    return problems


def test_repository_migration_chain_is_single_linear_and_unedited() -> None:
    assert chain_problems(VERSIONS) == []


def test_alembic_agrees_there_is_one_head_at_the_newest_revision() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    cfg = Config(str(ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT / "migrations"))
    script = ScriptDirectory.from_config(cfg)
    newest = max(r.revision for r in read_revisions(VERSIONS))
    assert script.get_heads() == [newest]
    assert [s.revision for s in script.walk_revisions()][-1] == "0001"


def _rev(n: int) -> str:
    return f"{n:04d}"


# The scenarios below add revisions on top of whatever the repository's head is today.
HEAD = max(r.revision for r in read_revisions(VERSIONS))
NEXT, AFTER = _rev(int(HEAD) + 1), _rev(int(HEAD) + 2)


def _copy_versions(tmp_path: Path) -> Path:
    target = tmp_path / "versions"
    shutil.copytree(VERSIONS, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def _write(path: Path, revision: str, down: str | None, table: str = "extra") -> None:
    path.write_text(
        f'revision = "{revision}"\ndown_revision = {down!r}\n\n\n'
        f"def upgrade() -> None:\n    op.create_table({table!r})\n",
        encoding="utf-8",
    )


def test_a_second_0003_like_the_two_open_prs_is_rejected(tmp_path: Path) -> None:
    """Reproduces H-01: PR #3's original hypotheses migration also claimed 0003 on top of 0002."""
    versions = _copy_versions(tmp_path)
    _write(versions / "0003_hypothesis_assessments.py", "0003", "0002", "hypothesis_assessments")
    problems = chain_problems(versions)
    assert any("'0003' defined more than once" in p for p in problems), problems
    assert any("'0002' has 2 children" in p for p in problems), problems


def test_two_heads_from_a_parallel_new_revision_are_rejected(tmp_path: Path) -> None:
    versions = _copy_versions(tmp_path)
    _write(versions / f"{NEXT}_a.py", NEXT, HEAD)
    _write(versions / f"{AFTER}_b.py", AFTER, HEAD)
    problems = chain_problems(versions)
    assert any("expected exactly one head" in p for p in problems), problems
    assert any(f"must revise '{NEXT}'" in p for p in problems), problems


def test_the_next_free_revision_is_accepted(tmp_path: Path) -> None:
    versions = _copy_versions(tmp_path)
    _write(versions / f"{NEXT}_next.py", NEXT, HEAD)
    assert chain_problems(versions) == []


@pytest.mark.parametrize(
    ("name", "revision", "down", "expected"),
    [
        (f"{NEXT}_x.py", AFTER, HEAD, "file name must start with its revision id"),
        (f"{_rev(int(HEAD) + 3)}_gap.py", _rev(int(HEAD) + 3), HEAD, "consecutive from 0001"),
        (f"{NEXT}_merge.py", NEXT, ("0003", HEAD), "must be one revision or None"),
        ("abcd_named.py", "abcd", HEAD, "must be four digits"),
    ],
)
def test_convention_breaks_are_named(tmp_path: Path, name: str, revision: str, down: object, expected: str) -> None:
    versions = _copy_versions(tmp_path)
    (versions / name).write_text(f'revision = "{revision}"\ndown_revision = {down!r}\n', encoding="utf-8")
    problems = chain_problems(versions)
    assert any(expected in p for p in problems), problems


def test_editing_or_renumbering_a_deployed_migration_is_rejected(tmp_path: Path) -> None:
    versions = _copy_versions(tmp_path)
    auth = versions / "0003_auth_users_sessions.py"
    auth.write_text(auth.read_text(encoding="utf-8") + "\n# harmless-looking edit\n", encoding="utf-8")
    assert any("deployed migration was edited" in p for p in chain_problems(versions))

    # Swapping the two 0003/0004 contents (the wrong fix for H-01) breaks the production pin.
    versions = _copy_versions(tmp_path / "swap")
    hyp = versions / "0004_hypothesis_assessments.py"
    auth = versions / "0003_auth_users_sessions.py"
    pins = {rev: ("", table) for rev, (_, table) in IMMUTABLE.items()}  # isolate the table check
    hyp_src = hyp.read_text(encoding="utf-8").replace('revision = "0004"', 'revision = "0003"')
    hyp_src = hyp_src.replace('down_revision = "0003"', 'down_revision = "0002"')
    auth_src = auth.read_text(encoding="utf-8").replace('revision = "0003"', 'revision = "0004"')
    auth_src = auth_src.replace('down_revision = "0002"', 'down_revision = "0003"')
    hyp.unlink()
    auth.unlink()
    (versions / "0003_hypothesis_assessments.py").write_text(hyp_src, encoding="utf-8")
    (versions / "0004_auth_users_sessions.py").write_text(auth_src, encoding="utf-8")
    problems = chain_problems(versions, immutable={**pins, "0001": ("", ""), "0002": ("", "")})
    assert "revision '0003' must create table 'users' (production history)" in problems, problems
