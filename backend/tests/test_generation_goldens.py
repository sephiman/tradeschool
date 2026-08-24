# SPDX-License-Identifier: AGPL-3.0-only
"""The cross-language generation goldens: one recipe, tied to the committed fingerprints.

Phase W2. `scripts/export_generation_goldens.py` writes the file the Kotlin port's generators are
compared against, document by document. Everything about that file is only as good as two properties,
and both are asserted here rather than described.

**One recipe.** The exporter hashes the same canonical bytes the committed goldens hash — the
`{"p": …, "label": …, "ann": …}` envelope for a pattern chart, `{"p", "t", "s1", "s2"}` for a
divergence, the `panels` list for a figure — so the exported digest's first 16 hex digits ARE the
committed fingerprint. That is checked for all 84 goldens and for the pins that name a document this
exporter produces. It is a stronger guard than sharing a function would be: if either side's
canonicalization drifts, the equality breaks, and it breaks naming the document.

**A transparent instrument.** The retry-loop seeds are found by counting iterations inside three
loops, which is done by rebinding what each loop body calls. A counter that changed a single float
would poison every golden it was used to select, so the fingerprints are asserted identical with the
instrument installed and without it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_generation_goldens import (  # noqa: E402
    FORMATTER_CASES,
    FORMATTER_ID,
    LOOPS_WITH_NO_RETRY_FOUND,
    MULTI_SEEDS,
    RETRY_LOOPS,
    SINGLE_SEEDS,
    canonical_json,
    document_sha256,
    exercise_documents,
    figure_documents,
    formatter_document,
    retry_iterations,
    scan_retry_loops,
)

from test_generation_numerics import PINNED  # type: ignore[import-not-found]  # noqa: E402
from test_golden_exercise_mode import GOLDEN, _fp  # type: ignore[import-not-found]  # noqa: E402


def test_the_exported_digest_is_the_committed_fingerprint_extended() -> None:
    """84 goldens, hashed by this exporter, must agree with the dict in the golden suite.

    The keys differ by design — the goldens say `fakeout:0`, the sweep says `fakeout:multi:0`,
    because the sweep also carries a single-target config for every label — so the mapping is spelled
    out rather than guessed at.
    """
    documents = dict(exercise_documents(multi_seeds=(0, 1, 2, 3), single_seeds=()))
    checked = 0
    for key, fingerprint in GOLDEN.items():
        name, seed = key.rsplit(":", 1)
        exported = f"divergence:rsi:golden:{seed}" if name == "divergence" else f"{name}:multi:{seed}"
        assert exported in documents, f"{key}: the sweep does not carry {exported}"
        digest = document_sha256(documents[exported])
        assert digest[:16] == fingerprint, f"{key}: exported {digest[:16]} != committed {fingerprint}"
        checked += 1
    assert checked == len(GOLDEN) == 84


def test_the_exporter_and_the_golden_suite_canonicalize_identically() -> None:
    """`document_sha256` and the suite's `_fp` must be the same bytes, not merely the same idea."""
    documents = dict(exercise_documents(multi_seeds=(0, 1), single_seeds=(0,)))
    assert documents
    for envelope in documents.values():
        assert document_sha256(envelope)[:16] == _fp(envelope)


def test_the_pinned_documents_this_exporter_produces_match_their_pins() -> None:
    """The 3 exercise pins and the 1 content-figure pin. The 2 SYNTHESIZED figure pins are not
    documents here — they are single-panel specs invented by the numerics suite, not content."""
    exercise = dict(exercise_documents(multi_seeds=(0, 1, 2, 3, 4), single_seeds=()))
    figures = dict(figure_documents())
    checked = 0
    for key, fingerprint in PINNED.items():
        space, name = key.split(":", 1)
        if space == "exercise":
            injector, seed = name.rsplit(":", 1)
            digest = document_sha256(exercise[f"{injector}:multi:{seed}"])
        elif space == "content":
            digest = document_sha256(figures[f"frozen:{name}"])
        else:
            continue  # a synthesized figure pin; see the docstring
        assert digest[:16] == fingerprint, f"{key}: exported {digest[:16]} != pinned {fingerprint}"
        checked += 1
    assert checked == 4, f"expected 4 checkable pins, checked {checked}"


def test_the_sizing_is_the_agreed_sizing() -> None:
    assert len(MULTI_SEEDS) == 100
    assert len(SINGLE_SEEDS) == 20
    assert MULTI_SEEDS[:20] == SINGLE_SEEDS, (
        "the single-target seeds must be a prefix of the multi-target ones, so a document appearing "
        "in both blocks is the same seed and a port debugging one is debugging the other"
    )


def test_the_two_files_carry_different_kinds_of_document() -> None:
    exercise = dict(exercise_documents(multi_seeds=(0,), single_seeds=(0,)))
    figures = dict(figure_documents())
    assert exercise and figures
    assert not set(exercise) & set(figures), "an id may only live in one of the two stability files"
    assert all(key.startswith("frozen:") for key in figures)
    # A figure document is the panels list; an exercise document is a keyed envelope. Different
    # shapes on purpose: each is the recipe its own committed fingerprint already uses.
    assert all(isinstance(value, list) for value in figures.values())
    assert all(isinstance(value, dict) for value in exercise.values())


def test_every_injector_and_every_label_is_covered() -> None:
    from tradeschool.exercises.charts.patterns.registry import all_injectors
    from tradeschool.exercises.charts.types import DivergenceType

    documents = dict(exercise_documents(multi_seeds=(0,), single_seeds=(0,)))
    for injector in all_injectors():
        assert f"{injector.name}:multi:0" in documents, injector.name
        for label in injector.labels:
            assert f"{injector.name}:{label}:0" in documents, f"{injector.name}:{label}"
    for indicator in ("rsi", "macd"):
        assert f"divergence:{indicator}:golden:0" in documents
        for target in DivergenceType:
            assert f"divergence:{indicator}:{target.value}:0" in documents


@pytest.mark.parametrize("loop", [loop.name for loop in RETRY_LOOPS])
def test_every_retry_loop_counter_is_actually_attached(loop: str) -> None:
    """A counter that saw nothing would report "no retries" for a loop that retries constantly."""
    from scripts.export_generation_goldens import _candidate_ids, instrumented, raw_for_id

    with instrumented() as counts:
        for seed in range(4):
            for _loop, identifier in _candidate_ids(seed):
                try:
                    retry_iterations(lambda i=identifier: raw_for_id(i), counts)
                except Exception:  # a refused plant is a designed outcome
                    continue
    assert counts[loop] > 0, f"{loop}: the counter never fired, so it is not attached"


def test_the_loops_that_retry_are_found_and_the_one_that_does_not_is_recorded() -> None:
    """Two of the three retry on real seeds; the third never has. Both halves are asserted.

    The `LOOPS_WITH_NO_RETRY_FOUND` half is the interesting one: it fails when a loop STARTS
    retrying, which is a change in generator behaviour and exactly the thing the goldens' retry-seed
    coverage would otherwise go quietly stale about.
    """
    findings = scan_retry_loops(scan_seeds=tuple(range(120)))
    retrying = {finding.loop for finding in findings}
    assert all(finding.iterations > 1 for finding in findings)
    for loop in RETRY_LOOPS:
        if loop.name in LOOPS_WITH_NO_RETRY_FOUND:
            assert loop.name not in retrying, (
                f"{loop.name} now retries — update LOOPS_WITH_NO_RETRY_FOUND and the exported "
                f"README, and add its seeds to the goldens"
            )
        else:
            assert loop.name in retrying, f"{loop.name}: no retrying seed in 0..119"
    assert set(LOOPS_WITH_NO_RETRY_FOUND) <= {loop.name for loop in RETRY_LOOPS}


def test_the_instrument_does_not_change_a_single_number() -> None:
    """A counter that perturbed the stream would silently corrupt every golden chosen with it."""
    from scripts.export_generation_goldens import instrumented

    plain = {key: document_sha256(value) for key, value in exercise_documents((0, 1, 2), ())}
    with instrumented() as counts:
        watched = {key: document_sha256(value) for key, value in exercise_documents((0, 1, 2), ())}
    assert watched == plain, "installing the retry counters moved a fingerprint"
    assert sum(counts.values()) > 0, "the counters saw nothing, so they were not installed"


def test_the_formatter_case_pins_what_a_naive_formatter_gets_wrong() -> None:
    """Python prints the shortest round-trip repr; Kotlin's `Double.toString` does not agree."""
    identifier, envelope = formatter_document()
    assert identifier == FORMATTER_ID
    text = canonical_json(envelope).decode()
    assert "e-" in text or "e+" in text, "no value serializes in exponential notation at all"
    assert any(case.python != case.jvm for case in FORMATTER_CASES), "nothing here would diverge"
    for case in FORMATTER_CASES:
        assert repr(case.value) == case.python, f"{case.name}: repr moved to {repr(case.value)!r}"
        assert case.python in text or case.name == "negative-zero", case.name


def test_one_id_resolves_the_same_way_alone_as_it_does_inside_the_sweep() -> None:
    """`--dump-id` must build the same document the file's line was hashed from, or debugging lies."""
    from scripts.export_generation_goldens import document_for_id

    swept = dict(exercise_documents((0, 7), (3,)))
    for key, envelope in swept.items():
        assert document_for_id(key) == envelope, key
    for key, envelope in figure_documents():
        assert document_for_id(key) == envelope, key
    # An id the sweep never emits — a retry seed past the single-target range — must resolve too.
    assert document_sha256(document_for_id("volatility_bands:expansion:35"))
    assert document_sha256(document_for_id(FORMATTER_ID)) == document_sha256(formatter_document()[1])


def test_the_dump_of_an_id_is_the_bytes_that_were_hashed() -> None:
    documents = dict(exercise_documents((0,), ()))
    key, envelope = next(iter(documents.items()))
    dumped = canonical_json(envelope)
    import hashlib

    assert hashlib.sha256(dumped).hexdigest() == document_sha256(envelope), key
    assert json.loads(dumped) == json.loads(canonical_json(envelope)), key


def test_each_loop_declares_what_an_iteration_means_in_it() -> None:
    """The three loops count differently — one excludes its own last resort — so each says so."""
    assert {loop.name for loop in RETRY_LOOPS} == {
        "divergence-plant",
        "cvd-divergence-plant",
        "squeeze-phase",
    }
    for loop in RETRY_LOOPS:
        assert loop.attempts >= 6, f"{loop.name}: an attempt budget of {loop.attempts} reads wrong"
        assert ":" in loop.where, f"{loop.name}: `where` must point at file:line, got {loop.where!r}"
        assert len(loop.counts.split()) > 8, f"{loop.name}: `counts` must say what it counts"
        assert loop.injectors, loop.name
    assert retry_iterations.__doc__
