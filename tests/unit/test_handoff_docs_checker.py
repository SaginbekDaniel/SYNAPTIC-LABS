"""Regression tests for ``docs/handoff/probes/check_handoff_docs.py``.

The checker guards the handoff documents a fresh session starts from. Its verdict must depend on the
shared repository, not on the container it runs in, and must neither miss a broken reference nor read
ordinary prose as one.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
CHECKER = ROOT / "docs" / "handoff" / "probes" / "check_handoff_docs.py"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_handoff_docs", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


chk = _load()


def _in_git_checkout() -> bool:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True).returncode == 0


needs_git = pytest.mark.skipif(not _in_git_checkout(), reason="needs the git checkout")


# -- path extraction ---------------------------------------------------------------------------
def test_slash_idiom_in_prose_is_not_a_path():
    # the reported false positive (ledger L-0015): "docs/test" means "docs and tests"
    assert chk.path_references("then the docs/test commit; working branch pushed.") == []


def test_the_same_token_in_code_is_still_checked():
    assert chk.path_references("see `docs/test`") == ["docs/test"]


@pytest.mark.parametrize(
    "prose",
    [
        "configs/detectors.yaml hypotheses.kinds",  # extension
        "the docs/handoff/ directory",  # trailing slash
        "edit src/nexora/api today",  # more than one segment below the top level
    ],
)
def test_unambiguous_prose_paths_are_still_checked(prose: str):
    assert len(chk.path_references(prose)) == 1


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("`docs/testing/x.md`", ["docs/testing/x.md"]),
        ("`tests/unit/test_x.py`", ["tests/unit/test_x.py"]),
        ("mydocs/handoff/x.md", []),  # not a top-level directory of this repository
        ("`apps/web/src/`.", ["apps/web/src/"]),
    ],
)
def test_similar_prefixes_are_not_conflated(text: str, expected: list[str]):
    assert chk.path_references(text) == expected


def test_existing_exemptions_are_kept():
    assert chk.path_references("`apps/web/src/x.ts` (new file)") == []
    assert chk.path_references("`docs/…` and `docs/*.md`") == []
    # a brace list stops the match: its directory prefix is what gets checked
    assert chk.path_references("`src/nexora/{a,b}.py`") == ["src/nexora/"]


def test_link_targets_and_fenced_blocks_count_as_code():
    text = "[state](docs/handoff/EXECUTION_STATE.md)\n```bash\ncat docs/x\n```\n"
    assert chk.path_references(text) == ["docs/handoff/EXECUTION_STATE.md", "docs/x"]


# -- path verification -------------------------------------------------------------------------
@needs_git
def test_broken_and_valid_references(tmp_path: Path):
    doc = tmp_path / "DOC.md"
    doc.write_text("`docs/handoff/EXECUTION_STATE.md` and `docs/handoff/NO_SUCH_FILE.md`; the docs/test commit\n")
    problems, checked, generated = chk.check_paths([doc], ROOT)
    assert problems == ["DOC.md: path does not exist: docs/handoff/NO_SUCH_FILE.md"]
    assert (checked, generated) == (2, 0)


@needs_git
def test_git_ignored_build_output_is_not_checked(tmp_path: Path):
    # exists only after `vite build`; the verdict must not depend on whether this machine built
    doc = tmp_path / "DOC.md"
    doc.write_text("`apps/web/public/vendor/mediapipe/`\n")
    assert chk.is_generated("apps/web/public/vendor/mediapipe/", ROOT)
    assert not chk.is_generated("docs/handoff/NO_SUCH_FILE.md", ROOT)
    assert chk.check_paths([doc], ROOT) == ([], 0, 1)


# -- commits -----------------------------------------------------------------------------------
def test_declared_local_commit_is_recognised():
    refs = chk.sha_references("(local commit `6cb45bb`, gate green) then `ea5ca9c` and migration `0003`")
    assert refs == [("6cb45bb", True), ("ea5ca9c", False)]  # all-digit tokens are revision numbers, not SHAs


@needs_git
def test_unknown_and_unpublished_commits_are_reported():
    reachable = chk.reachable_commits(ROOT)
    head = next(c for c in sorted(reachable) if not c[:7].isdigit())
    text = f"`{head[:7]}` · `deadbee` · local commit `fadedad`"
    assert chk.check_commits("DOC.md", text, reachable, ROOT) == ["DOC.md: commit not found: deadbee"]
    # a commit that exists in this object store but on no published ref is invisible to the next session
    assert chk.check_commits("DOC.md", f"`{head[:7]}`", reachable - {head}, ROOT) == [
        f"DOC.md: commit {head[:7]} exists only locally (not reachable from HEAD or origin)"
    ]
