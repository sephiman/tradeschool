# SPDX-License-Identifier: AGPL-3.0-only
"""The libm-parity contract: what crosses to the Android repository, and that it is a COPY.

Phase W2. The other two contract exporters compute what they write, so their tests can recompute and
compare. This one must not: the parity measurement's entire value is that it was taken once, on a
recorded machine against a recorded glibc, and an export that quietly re-measured would re-baseline
the very thing being pinned — on whatever libc happens to be installed the day someone runs it.

So the load-bearing assertion here is byte-identity with the recorded artifact, and the second one is
that the README cannot drift away from the numbers in it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_libm_parity import (  # noqa: E402
    DELIVERED,
    REGENERATE,
    ParityExportError,
    deliver,
    missing_sources,
    readme_text,
)


@pytest.fixture(scope="module")
def exported(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("libm-parity")
    deliver(out)
    return out


def test_the_recorded_artifacts_are_all_present_to_be_copied() -> None:
    """If this fails the repository lost a measurement, and no other test here means anything."""
    assert missing_sources() == [], (
        "the recorded parity artifacts are missing from backend/scripts/ — this exporter copies "
        f"rather than re-measures, so restore them or re-record with `{REGENERATE}`"
    )


def test_every_delivered_file_is_byte_identical_to_what_was_recorded(exported: Path) -> None:
    """The one guarantee: an export copies the measurement, it never takes a new one.

    A re-measurement would be invisible — same filenames, same shape, plausible numbers — and would
    silently rebaseline the port's reference against whichever libc ran the export.
    """
    for source, name, _what in DELIVERED:
        assert (exported / name).read_bytes() == source.read_bytes(), name


def test_the_readme_ships_beside_them_and_is_the_only_generated_file(exported: Path) -> None:
    delivered = {name for _source, name, _what in DELIVERED}
    assert {path.name for path in exported.iterdir()} == delivered | {"README.md"}


def test_a_missing_artifact_refuses_and_says_how_to_get_it_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A short directory in the other repository is indistinguishable from a complete one."""
    import scripts.export_libm_parity as exporter

    absent = tmp_path / "gone" / "libm-parity-sample.tsv"
    monkeypatch.setattr(
        exporter, "DELIVERED", ((absent, "libm-parity-sample.tsv", "the measured rows"),)
    )
    out = tmp_path / "out"
    with pytest.raises(ParityExportError, match="missing artifact") as refusal:
        exporter.deliver(out)
    assert "libm-parity-sample.tsv" in str(refusal.value)
    assert REGENERATE in str(refusal.value), "a refusal must carry the command that fixes it"
    assert not out.exists(), "a refused export writes nothing"


def test_a_second_export_replaces_rather_than_leaving_a_stale_measurement(tmp_path: Path) -> None:
    out = tmp_path / "out"
    deliver(out)
    stale = out / "libm-parity-sample-from-2019.tsv"
    stale.write_text("fn\tinput\n", encoding="utf-8")
    deliver(out)
    assert not stale.exists(), "a leftover artifact is a second opinion about what glibc returned"


# --- the README cannot drift from the artifact it describes -----------------------------------------


def test_the_readme_reports_the_numbers_the_summary_actually_holds(exported: Path) -> None:
    """Every figure in the prose is interpolated from the artifacts, so it moves when they do."""
    summary = json.loads((exported / "libm-parity-summary.json").read_text(encoding="utf-8"))
    domain = json.loads((exported / "libm-parity-domain.json").read_text(encoding="utf-8"))
    readme = (exported / "README.md").read_text(encoding="utf-8")

    assert readme == readme_text(summary, domain), "the shipped README is not the generated one"
    assert summary["environment"]["libc"] in readme
    for function, measured in summary["functions"].items():
        assert f"`{function}`" in readme
        assert f"{measured['calls']:,}" in readme
        assert measured["digests"]["inputs"] in readme, "the full-stream digest is how --full is checked"
        assert repr(domain["domains"][function]["max"]) in readme


def test_the_readme_states_the_rule_that_keeps_this_out_of_a_build(exported: Path) -> None:
    """The port must report the mismatch count, never fail on it — and the shipped checker exits 1.

    `LibmParityCheck.java` answers Phase W1's stricter question and returns non-zero on this very
    artifact. Someone wiring it to CI is the failure this paragraph exists to prevent.
    """
    readme = (exported / "README.md").read_text(encoding="utf-8")
    assert "Never fail on it" in readme
    assert "do not wire its exit code to a build" in readme
    assert "`StrictMath`, never `Math`" in readme
    assert "generation-goldens" in readme, "the binding contract must be named, not implied"
