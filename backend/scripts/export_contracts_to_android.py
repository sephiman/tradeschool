# SPDX-License-Identifier: AGPL-3.0-only
"""Copy `dist/bundle` and `dist/contracts` into the Android repository, with a provenance manifest.

Phase W2, and the ONLY sanctioned transfer path between the two repositories. Not because copying is
hard, but because the failure mode of an ad-hoc `cp -r` is quiet: a half-updated bundle, or a set of
goldens nobody can trace back to a commit three weeks later when one of them disagrees. So there is
one script, and it writes down what it did.

What it writes. `EXPORT_MANIFEST.json` at the target's root: this repo's HEAD, whether the working
tree was dirty and which files were uncommitted, the bundle's own content fingerprint, every delivered
file with its sha256, and when. That is enough to answer "which content is this app built from?"
without asking anyone.

What it refuses. It never creates the target and never touches anything in it outside `bundle/`,
`contracts/` and the manifest — that repository is somebody's working tree with its own history. It
refuses a target that is not a git repository, because pinning a source commit against a destination
nobody can identify is not provenance. And it REPLACES the two directories rather than merging into
them: a lesson left behind by an earlier export is a bundle shipping two versions of a page.

The dirty flag is the load-bearing honesty. An export taken from a working tree with uncommitted
changes says so and lists them, so a manifest can never imply that a clean commit produced artifacts
built from unstaged edits. Re-run after committing and the flag clears.

Usage (from `backend/`):
    uv run python scripts/export_contracts_to_android.py --target /path/to/tradeschool-android
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
REPO = _BACKEND.parent
DEFAULT_SOURCE = REPO / "dist"

#: The two directories that cross the repository boundary, and nothing else. Named here so the
#: "touches nothing outside these" promise is one list rather than a habit.
DELIVERED_DIRS = ("bundle", "contracts")

#: Every contract directory that must exist before a delivery, and the script that produces it.
#: Without this, forgetting one exporter ships a `contracts/` that looks complete: the Android repo
#: receives a manifest listing exactly what it was sent and has no way to know what it was not.
REQUIRED_CONTRACT_DIRS = {
    "prng-vectors": "export_prng_vectors.py",
    "generation-goldens": "export_generation_goldens.py",
    "libm-parity": "export_libm_parity.py",
}

MANIFEST_NAME = "EXPORT_MANIFEST.json"

#: What a dirty export means, carried in the manifest itself rather than left to a reader's memory.
DIRTY_NOTE = (
    "The source working tree had uncommitted changes when this export ran, so `commit` names the "
    "parent of the content that actually produced these files. Re-run the export after committing "
    "so the manifest points at a clean commit."
)


class DeliveryError(RuntimeError):
    """The export would have written somewhere it should not, or from something it should not."""


#: Porcelain v1 prefixes each entry with two status columns and a space, then the path.
_STATUS_WIDTH = 2

#: The status codes whose entry carries a SECOND path: rename and copy.
_RENAME_CODES = frozenset("RC")


def _git(repo: Path, *args: str, raw: bool = False) -> str:
    """Run git and return its stdout, stripped — `raw=True` for output parsed by position."""
    result = subprocess.run(
        ["git", *args], cwd=repo, check=False, capture_output=True, text=True
    )
    if result.returncode != 0:
        raise DeliveryError(f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}")
    return result.stdout if raw else result.stdout.strip()


def is_git_repo(path: Path) -> bool:
    return (path / ".git").exists()


def git_head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD")


def working_tree_changes(repo: Path) -> list[str]:
    """Every path git reports as modified, staged or untracked, both halves of a rename included.

    `-z` because this is parsed by position: paths come raw and NUL-terminated, so none is quoted and
    a rename is two fields rather than one `old -> new` string. `-uall` so a directory names its files.
    """
    fields = _git(repo, "status", "--porcelain=v1", "-z", "-uall", raw=True).split("\0")
    paths: list[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) <= _STATUS_WIDTH + 1:  # the terminating NUL leaves one empty field
            continue
        status, path = entry[:_STATUS_WIDTH], entry[_STATUS_WIDTH + 1 :]
        paths.append(path)
        if set(status) & _RENAME_CODES and index < len(fields):
            paths.append(fields[index])  # a rename names its destination first, then its source
            index += 1
    return sorted(paths)


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _delivered_files(target: Path) -> dict[str, str]:
    """Every delivered file by target-relative path, sha256'd. The manifest itself is not in it."""
    files: dict[str, str] = {}
    for name in DELIVERED_DIRS:
        for path in sorted((target / name).rglob("*")):
            if path.is_file():
                files[path.relative_to(target).as_posix()] = sha256_file(path)
    return files


def deliver(source: Path, target: Path, *, now: str | None = None) -> dict[str, Any]:
    """Copy the two directories and write the manifest. Returns the manifest it wrote."""
    if not target.exists():
        raise DeliveryError(
            f"the target {target} does not exist. This script does not create it: the Android "
            f"repository is checked out by hand, and creating a lookalike would deliver artifacts "
            f"somewhere nobody is looking."
        )
    if not target.is_dir():
        raise DeliveryError(f"the target {target} is not a directory")
    if not is_git_repo(target):
        raise DeliveryError(
            f"the target {target} is not a git repository. The manifest pins a source commit against "
            f"a destination, and a destination with no history cannot hold up its end."
        )
    for name in DELIVERED_DIRS:
        if not (source / name).is_dir():
            raise DeliveryError(
                f"{source / name} does not exist — run `export_bundle.py` and every script in "
                f"{sorted(REQUIRED_CONTRACT_DIRS.values())} first"
            )
    absent = {
        name: script
        for name, script in sorted(REQUIRED_CONTRACT_DIRS.items())
        if not (source / "contracts" / name).is_dir()
    }
    if absent:
        detail = ", ".join(f"{name}/ (`{script}`)" for name, script in absent.items())
        raise DeliveryError(
            f"the contract set is incomplete — missing {detail}. Delivering a partial `contracts/` "
            f"would give the Android repository a manifest it cannot tell is short."
        )

    bundle_manifest = json.loads((source / "bundle" / "manifest.json").read_text(encoding="utf-8"))

    for name in DELIVERED_DIRS:
        destination = target / name
        if destination.exists():
            shutil.rmtree(destination)
        # Nothing hidden crosses the boundary: a `.ast-input.json` left behind by a failed export is
        # a debugging aid in this repo and a mystery file in the other one.
        shutil.copytree(source / name, destination, ignore=shutil.ignore_patterns(".*"))

    files = _delivered_files(target)
    changes = working_tree_changes(REPO)
    manifest: dict[str, Any] = {
        "exportedAt": now or datetime.now(UTC).isoformat(),
        "sourceRepo": {
            "path": str(REPO),
            "commit": git_head(REPO),
            "branch": _git(REPO, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(changes),
            "uncommittedFiles": changes,
            **({"note": DIRTY_NOTE} if changes else {}),
        },
        "bundleFormatVersion": bundle_manifest.get("bundleFormatVersion"),
        "bundleFingerprint": bundle_manifest.get("contentFingerprint"),
        "counts": {
            name: sum(1 for key in files if key.startswith(f"{name}/")) for name in DELIVERED_DIRS
        },
        "files": files,
    }
    (target / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="the Android repository's root (must exist, must be a git repo)",
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help=f"default {DEFAULT_SOURCE}")
    args = parser.parse_args(argv)

    manifest = deliver(args.source, args.target)
    source_repo = manifest["sourceRepo"]

    print("=" * 78)
    print(f"DELIVERED TO  {args.target}")
    print("=" * 78)
    print(f"from              {args.source}")
    print(f"source commit     {source_repo['commit']}  ({source_repo['branch']})")
    print(f"dirty             {source_repo['dirty']}"
          + (f"  — {len(source_repo['uncommittedFiles'])} uncommitted paths" if source_repo["dirty"] else ""))
    print(f"bundle format     {manifest['bundleFormatVersion']}")
    print(f"bundle print      {manifest['bundleFingerprint']}")
    for name in DELIVERED_DIRS:
        print(f"{name + '/':<18}{manifest['counts'][name]} files")
    print(f"manifest          {MANIFEST_NAME} ({len(manifest['files'])} files digested)")
    print(f"exported at       {manifest['exportedAt']}")
    print()
    print(f"Nothing outside {', '.join(f'{d}/' for d in DELIVERED_DIRS)} and {MANIFEST_NAME} was touched.")
    if source_repo["dirty"]:
        print()
        print("THIS EXPORT IS FROM A DIRTY TREE. Re-run it after committing:")
        print(f"  cd {_BACKEND} && uv run python scripts/export_contracts_to_android.py "
              f"--target {args.target}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except DeliveryError as error:
        print(f"\nDELIVERY REFUSED\n{error}", file=sys.stderr)
        raise SystemExit(2) from None
