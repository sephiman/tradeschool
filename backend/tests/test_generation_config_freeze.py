# SPDX-License-Identifier: AGPL-3.0-only
"""The frozen configs: the exact inputs behind every digest in `exercise-mode.tsv`.

Phase W2. A golden is a promise about a document, and a document is a config plus a seed. The
digests travelled to the Android repository without the configs, which made the promise
unverifiable from the other side: a port that rebuilt a config from prose could match the shape and
miss the identity.

**Why byte-identical and not equivalent.** `targets` feeds `rng.integers(0, len(targets))`, so the
LENGTH of that list decides which label a seed lands on. A config with the same meaning and a
different target count generates a different document from the same seed — silently, and for every
seed at once. `test_dropping_one_target_moves_the_document` is that failure made visible.

The chain asserted here runs all the way through: the config the exporter derives from the registry,
serialized, written to disk, read back, re-parsed by the generator's own `parse_config`, instantiated
at the seed a committed fingerprint names, and hashed. If any link drifts, the fingerprint moves.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_bundle import canonical_bytes  # noqa: E402
from scripts.export_generation_goldens import (  # noqa: E402
    CONFIG_DIR_NAME,
    CONFIG_INDEX_NAME,
    FORMATTER_ID,
    _config_and_kind,
    canonical_json,
    config_documents,
    config_key_of,
    config_relative_path,
    document_sha256,
    envelope_of,
    exercise_ids,
    parse_config_document,
    raw_from_config,
    write_configs,
)

from test_golden_exercise_mode import GOLDEN  # type: ignore[import-not-found]  # noqa: E402


def _all_ids() -> list[str]:
    return [*exercise_ids(), FORMATTER_ID]


def _frozen(tmp_path: Path) -> dict[str, dict[str, object]]:
    """Write the configs the way the exporter does, then read them back off disk.

    Read back rather than reused in memory: the contract is the BYTES the Android repository
    receives, and a test that never leaves Python cannot tell a serializer bug from a dict.
    """
    documents = config_documents(_all_ids())
    write_configs(tmp_path, documents)
    out: dict[str, dict[str, object]] = {}
    for key in documents:
        path = tmp_path / CONFIG_DIR_NAME / config_relative_path(key)
        out[key] = json.loads(path.read_bytes().decode("utf-8"))
    return out


def test_every_document_id_names_a_frozen_config() -> None:
    """No id may resolve to a config the Android repository was not sent."""
    documents = config_documents(_all_ids())
    for identifier in _all_ids():
        key = config_key_of(identifier)
        if key is None:
            assert identifier == FORMATTER_ID, f"{identifier}: only the formatter case has no config"
            continue
        assert key in documents, f"{identifier}: no frozen config for {key}"
    assert config_key_of(FORMATTER_ID) is None
    assert config_key_of("frozen:fig-m03-trend-vs-range") is None


def test_the_config_key_of_an_id_resolves_the_config_that_id_uses() -> None:
    """Stripping the seed must not change which config an id names, or the freeze is off by one."""
    for identifier in (
        "fakeout:multi:7",
        "fakeout:false_break:3",
        "divergence:rsi:golden:0",
        "divergence:macd:bearish_hidden:149",
        "volatility_bands:expansion:35",
    ):
        key = config_key_of(identifier)
        assert key is not None
        config, kind = _config_and_kind(identifier)
        keyed_config, keyed_kind = _config_and_kind(key)
        assert keyed_config == config, identifier
        assert keyed_kind == kind, identifier


def test_the_frozen_bytes_are_the_bundles_recipe_and_not_the_goldens_one(tmp_path: Path) -> None:
    """Two canonical forms live in this repo and they differ. This directory uses the bundle's.

    The goldens' recipe leaves `ensure_ascii` on and writes no trailing newline; the bundle's does the
    opposite so the TypeScript half can write byte-identical files. A config carrying a localized
    prompt with an accent serializes differently under the two, so which one applies is pinned here
    rather than left to whichever import a future edit reaches for.
    """
    documents = config_documents(_all_ids())
    write_configs(tmp_path, documents)
    for key, document in documents.items():
        written = (tmp_path / CONFIG_DIR_NAME / config_relative_path(key)).read_bytes()
        assert written == canonical_bytes(document), key
        assert written.endswith(b"\n"), f"{key}: the bundle recipe ends in a newline"
        assert written != canonical_json(document), f"{key}: this is the goldens' recipe, not the bundle's"


def test_a_frozen_config_reparses_into_the_config_it_was_written_from(tmp_path: Path) -> None:
    """Lossless, through the generator's own `parse_config` — the door the app uses too."""
    frozen = _frozen(tmp_path)
    assert frozen
    for key, document in frozen.items():
        expected, kind = _config_and_kind(key)
        assert parse_config_document(document, kind) == expected, key


def test_a_document_built_from_the_frozen_config_matches_its_committed_fingerprint(
    tmp_path: Path,
) -> None:
    """The load-bearing one: frozen bytes off disk must reproduce the 84 committed goldens.

    The key mapping is the golden suite's own — `fakeout:0` is the multi-target config, and the bare
    `divergence:N` goldens are the three-target list, not the five-target one.
    """
    frozen = _frozen(tmp_path)
    checked = 0
    for golden_key, fingerprint in GOLDEN.items():
        name, seed = golden_key.rsplit(":", 1)
        key = "divergence:rsi:golden" if name == "divergence" else f"{name}:multi"
        assert key in frozen, golden_key
        _config, kind = _config_and_kind(key)
        config = parse_config_document(frozen[key], kind)
        digest = document_sha256(envelope_of(kind, raw_from_config(config, kind, int(seed))))
        assert digest[:16] == fingerprint, (
            f"{golden_key}: the frozen config produced {digest[:16]}, committed {fingerprint}"
        )
        checked += 1
    assert checked == len(GOLDEN) == 84


def test_dropping_one_target_moves_the_document(tmp_path: Path) -> None:
    """The teeth. `rng.integers(0, len(targets))` means a shorter list is a different document.

    Mutated so it still VALIDATES — every target is still among the choices — because a config that
    merely fails to parse would prove nothing about identity.
    """
    frozen = _frozen(tmp_path)
    key = "fakeout:multi"
    _config, kind = _config_and_kind(key)
    intact = frozen[key]
    targets = intact["targets"]
    assert isinstance(targets, list), key
    assert len(targets) == 3, "this test needs a multi-target config to shorten"

    faithful = document_sha256(
        envelope_of(kind, raw_from_config(parse_config_document(intact, kind), kind, 0))
    )
    mutated = dict(intact, targets=targets[:-1])
    moved = document_sha256(envelope_of(kind, raw_from_config(parse_config_document(mutated, kind), kind, 0)))
    assert faithful != moved, (
        "dropping a target left the document unchanged, so this directory's byte-identical "
        "requirement is not actually load-bearing and the assertion above has no teeth"
    )
    assert faithful[:16] == GOLDEN["fakeout:0"]


def test_changing_the_bar_count_moves_the_document(tmp_path: Path) -> None:
    """`n` is not a tuning knob either: a different bar count is a different document."""
    frozen = _frozen(tmp_path)
    key = "fakeout:multi"
    _config, kind = _config_and_kind(key)
    intact = frozen[key]
    assert intact["n"] == 130
    faithful = document_sha256(
        envelope_of(kind, raw_from_config(parse_config_document(intact, kind), kind, 0))
    )
    moved = document_sha256(
        envelope_of(kind, raw_from_config(parse_config_document(dict(intact, n=131), kind), kind, 0))
    )
    assert faithful != moved


def test_the_path_of_a_config_is_derived_safely_and_uniquely() -> None:
    """A key is a colon-joined id fragment and a path is not, so the mapping is checked both ways."""
    documents = config_documents(_all_ids())
    paths = {key: config_relative_path(key) for key in documents}
    assert len(set(paths.values())) == len(paths), "two configs share a path"
    for key, relative in paths.items():
        assert ":" not in relative, key
        assert relative.endswith(".json"), key
        assert ".." not in Path(relative).parts, key
        assert not Path(relative).is_absolute(), key
        assert Path(relative).parts[0] in ("pattern", "divergence"), key
    assert paths["fakeout:multi"] == "pattern/fakeout/multi.json"
    assert paths["divergence:rsi:golden"] == "divergence/rsi/golden.json"
    assert paths["divergence:macd:bearish_hidden"] == "divergence/macd/bearish_hidden.json"


def test_the_index_lists_every_config_with_the_hash_of_its_own_bytes(tmp_path: Path) -> None:
    """ "Frozen alongside its hashes" — so a port can verify the file it read before trusting it."""
    import hashlib

    documents = config_documents(_all_ids())
    write_configs(tmp_path, documents)
    index = (tmp_path / CONFIG_DIR_NAME / CONFIG_INDEX_NAME).read_text(encoding="utf-8")
    rows = [line.split("\t") for line in index.splitlines() if line and not line.startswith("#")]
    header, body = rows[0], rows[1:]
    assert header == ["config", "path", "sha256"]
    assert len(body) == len(documents)
    assert body == sorted(body), "the index must be sorted, or a re-export diffs by row order"
    for key, relative, digest in body:
        assert relative == config_relative_path(key)
        written = (tmp_path / CONFIG_DIR_NAME / relative).read_bytes()
        assert hashlib.sha256(written).hexdigest() == digest, key


def test_the_frozen_set_is_the_agreed_shape() -> None:
    """22 multi-target configs and one per injector-label pair, counted rather than described."""
    documents = config_documents(_all_ids())
    multi = [key for key in documents if key.endswith(":multi") or key.endswith(":golden")]
    assert len(multi) == 22, f"expected 20 injectors + 2 oscillators, got {len(multi)}"
    assert len(documents) == 107, f"the frozen config set changed size: {len(documents)}"
