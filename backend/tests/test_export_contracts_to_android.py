# SPDX-License-Identifier: AGPL-3.0-only
"""The one sanctioned way artifacts cross into the Android repository, and what it refuses to do.

Phase W2. `dist/bundle` and `dist/contracts` are built here and consumed there, and the failure mode
of an ad-hoc `cp -r` is not a broken build: it is a bundle that half-updated, or one whose provenance
nobody can reconstruct three weeks later when a golden disagrees. So there is one script, it writes
an `EXPORT_MANIFEST.json` recording exactly which commit of this repo produced what, and it is
deliberately narrow about the target directory:

  * it never creates the target, and never touches anything in it outside `bundle/`, `contracts/` and
    the manifest — the Android repo is somebody's working tree, with its own history;
  * it REPLACES those two directories rather than merging into them, because a stale lesson left
    behind by a previous export is a bundle shipping two versions of a page;
  * it refuses a target that is not a git repository, since the whole point of the manifest is to pin
    a source commit against a destination commit.

The dirty flag is the honest part. The export records this repo's HEAD, and if the working tree has
uncommitted changes it says so and lists them — so a manifest can never imply that a clean commit
produced artifacts that were actually built from unstaged edits.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_contracts_to_android import (  # noqa: E402
    DELIVERED_DIRS,
    MANIFEST_NAME,
    DeliveryError,
    deliver,
    git_head,
    working_tree_changes,
)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


@pytest.fixture
def source(tmp_path: Path) -> Path:
    """A miniature `dist/` — the two delivered directories and a bundle manifest with a fingerprint."""
    dist = tmp_path / "dist"
    (dist / "bundle" / "ast" / "es").mkdir(parents=True)
    (dist / "bundle" / "ast" / "es" / "m01-l1.json").write_text('{"ast":{}}\n', encoding="utf-8")
    (dist / "bundle" / "manifest.json").write_text(
        json.dumps({"bundleFormatVersion": 1, "contentFingerprint": "f" * 64}), encoding="utf-8"
    )
    (dist / "contracts" / "prng-vectors").mkdir(parents=True)
    (dist / "contracts" / "prng-vectors" / "seedsequence.tsv").write_text("seed\n0\n", encoding="utf-8")
    return dist


@pytest.fixture
def target(tmp_path: Path) -> Path:
    """A git repo that already has content of its own, which the export must leave alone."""
    repo = tmp_path / "android"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "LICENSE").write_text("license text\n", encoding="utf-8")
    (repo / "docs").mkdir()
    (repo / "docs" / "port.md").write_text("# notes\n", encoding="utf-8")
    return repo


def test_a_missing_target_stops_and_creates_nothing(source: Path, tmp_path: Path) -> None:
    missing = tmp_path / "not-there"
    with pytest.raises(DeliveryError, match="does not exist"):
        deliver(source, missing)
    assert not missing.exists(), "a missing target must be reported, never created"


def test_a_target_that_is_not_a_git_repository_stops(source: Path, tmp_path: Path) -> None:
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(DeliveryError, match="not a git repository"):
        deliver(source, plain)
    assert list(plain.iterdir()) == [], "nothing may be written into a refused target"


def test_a_missing_source_stops(target: Path, tmp_path: Path) -> None:
    with pytest.raises(DeliveryError, match="bundle"):
        deliver(tmp_path / "empty-dist", target)


def test_the_two_directories_and_the_manifest_are_delivered(source: Path, target: Path) -> None:
    manifest = deliver(source, target)
    for name in DELIVERED_DIRS:
        assert (target / name).is_dir(), name
    assert (target / "bundle" / "ast" / "es" / "m01-l1.json").read_text() == '{"ast":{}}\n'
    assert (target / MANIFEST_NAME).exists()
    assert json.loads((target / MANIFEST_NAME).read_text()) == manifest


def test_nothing_outside_the_two_directories_and_the_manifest_is_touched(
    source: Path, target: Path
) -> None:
    before = {
        str(path.relative_to(target)): path.read_bytes()
        for path in target.rglob("*")
        if path.is_file() and ".git/" not in str(path.relative_to(target))
    }
    deliver(source, target)
    for relative, content in before.items():
        assert (target / relative).read_bytes() == content, f"{relative} was modified"
    allowed = {*DELIVERED_DIRS, MANIFEST_NAME, ".git", *(Path(p).parts[0] for p in before)}
    assert {path.name for path in target.iterdir()} <= allowed


def test_a_second_export_replaces_rather_than_merges(source: Path, target: Path) -> None:
    """A lesson left behind by an earlier export is a bundle carrying two versions of a page."""
    deliver(source, target)
    stale = target / "bundle" / "ast" / "es" / "m99-l9.json"
    stale.write_text('{"ast":{"stale":true}}\n', encoding="utf-8")
    manifest = deliver(source, target)
    assert not stale.exists(), "the stale file survived the export"
    assert "bundle/ast/es/m99-l9.json" not in manifest["files"]


def test_the_manifest_records_provenance_that_can_be_checked(source: Path, target: Path) -> None:
    import hashlib

    manifest = deliver(source, target)
    assert manifest["sourceRepo"]["commit"] == git_head(_BACKEND.parent)
    assert len(manifest["sourceRepo"]["commit"]) == 40
    assert manifest["bundleFingerprint"] == "f" * 64
    assert manifest["exportedAt"].endswith("+00:00") or manifest["exportedAt"].endswith("Z")
    assert manifest["files"], "an empty file list would make the manifest unverifiable"
    for relative, digest in manifest["files"].items():
        path = target / relative
        assert path.is_file(), relative
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, relative
    assert MANIFEST_NAME not in manifest["files"], "the manifest cannot digest itself"
    assert set(manifest["counts"]) == {"bundle", "contracts"}


def test_a_dirty_source_tree_is_declared_and_its_files_listed(source: Path, target: Path) -> None:
    """The one thing a provenance manifest must never do is imply a clean commit it did not have."""
    manifest = deliver(source, target)
    changes = working_tree_changes(_BACKEND.parent)
    assert manifest["sourceRepo"]["dirty"] is bool(changes)
    assert manifest["sourceRepo"]["uncommittedFiles"] == changes
    if changes:
        assert manifest["sourceRepo"]["note"], "a dirty export must say what that means"


def test_the_timestamp_can_be_pinned_so_two_exports_are_comparable(
    source: Path, target: Path
) -> None:
    first = deliver(source, target, now="2026-08-24T00:00:00+00:00")
    second = deliver(source, target, now="2026-08-24T00:00:00+00:00")
    assert first == second, "the same inputs and the same clock must give the same manifest"


@pytest.fixture
def dirty_repo(tmp_path: Path) -> Path:
    """A repo dirtied in the four ways porcelain reports differently, dotfile first."""
    repo = tmp_path / "source"
    repo.mkdir()
    _git(repo, "init", "-q")
    _git(repo, "config", "user.email", "t@example.com")
    _git(repo, "config", "user.name", "t")
    for name in (".gitignore", "README.md", "a.txt", "with space.txt"):
        (repo / name).write_text("before\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "init")
    (repo / ".gitignore").write_text("after\n", encoding="utf-8")
    (repo / "with space.txt").write_text("after\n", encoding="utf-8")
    _git(repo, "mv", "a.txt", "b.txt")
    (repo / "untracked.txt").write_text("new\n", encoding="utf-8")
    return repo


def test_a_leading_dot_survives_on_the_first_reported_path(dirty_repo: Path) -> None:
    """`.gitignore` sorts first, and the first line is the one a stripped output shifts by a char."""
    assert ".gitignore" in working_tree_changes(dirty_repo)


def test_a_rename_records_both_of_its_paths_and_no_arrow(dirty_repo: Path) -> None:
    changes = working_tree_changes(dirty_repo)
    assert "a.txt" in changes, "the path the rename left is evidence too"
    assert "b.txt" in changes
    assert [p for p in changes if "->" in p] == [], "a rename is two paths, never one string"


def test_a_path_containing_a_space_is_recorded_unquoted(dirty_repo: Path) -> None:
    assert "with space.txt" in working_tree_changes(dirty_repo)


def test_every_dirty_path_is_reported_exactly_once(dirty_repo: Path) -> None:
    changes = working_tree_changes(dirty_repo)
    assert changes == sorted(changes)
    assert len(changes) == len(set(changes))
    assert set(changes) == {
        ".gitignore", "with space.txt", "a.txt", "b.txt", "untracked.txt",
    }
