# SPDX-License-Identifier: AGPL-3.0-only
"""The PRNG contract the Kotlin port must reproduce, and the instruments that measure it.

Phase W2. Every number in every chart and every shuffled option list comes out of one of two random
number generators — NumPy's PCG64 for the charts, CPython's Mersenne Twister for the exercise
machinery — and the port has to reproduce both bit for bit or nothing downstream can be compared.
`scripts/export_prng_vectors.py` writes the vectors it will be checked against; this file asserts the
vectors describe what they claim to.

Three of the contracts are not obvious and are the reason this file exists rather than a README:

  * **Seeding.** `default_rng(seed)` is `SeedSequence(seed)` expanded to four 64-bit words and then
    fed through `pcg64_srandom_r`, which is two LCG steps around an addition. A port that skips
    either step, or orders the words differently, gets a plausible-looking stream that shares not one
    value with this one. The whole chain is asserted here, in Python arithmetic, against NumPy's own
    initial state.
  * **The 32-bit buffer.** `next_uint32` splits one 64-bit draw in half and hands out the LOW half
    first, keeping the high half in `uinteger`. Get that backwards and every 32-bit draw is wrong
    while every 64-bit draw is right — which is the hardest kind of bug to see.
  * **The ziggurat tail.** `normal()` returns from a table lookup 99% of the time and from a
    `log`-based tail otherwise, and only the tail (and the wedge test's `exp`) can differ between two
    correct libms. Which draws take which path is not observable from the values alone, so the
    instrument counts the 64-bit words each draw consumes and proves that the count and the value
    together identify the path.
"""

from __future__ import annotations

import itertools
import random
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_prng_vectors import (  # noqa: E402
    DRAWS_PER_SEED,
    MIXED_PROGRAM,
    NARROW_OPS,
    VECTOR_SEEDS,
    WIDE_OPS,
    ZIGGURAT_NOR_R,
    build_all,
    cpython_mt_state,
    mixed_rows,
    normal_rows,
    pcg64_state_from_words,
    quiz_layout_rows,
    seed_state_words,
)


def test_the_seeding_chain_is_reproduced_from_the_exported_words() -> None:
    """SeedSequence -> four words -> `pcg64_srandom_r` -> the state NumPy actually starts from."""
    for seed in VECTOR_SEEDS:
        words = seed_state_words(seed, count=4)
        predicted = pcg64_state_from_words(words)
        actual = np.random.default_rng(seed).bit_generator.state["state"]
        assert predicted == actual, f"seed {seed}: derived PCG64 state does not match NumPy's"


def test_the_32_bit_words_are_the_64_bit_words_split_little_endian() -> None:
    """The uint32 view of a SeedSequence is not a second stream; a port needs to know which."""
    for seed in VECTOR_SEEDS[:4]:
        wide = seed_state_words(seed, count=4)
        narrow = seed_state_words(seed, count=8, bits=32)
        for index, word in enumerate(wide):
            assert narrow[2 * index] == word & 0xFFFFFFFF, seed
            assert narrow[2 * index + 1] == word >> 32, seed


def test_a_buffered_32_bit_draw_hands_out_the_low_half_first() -> None:
    """The trap: `uinteger` holds the HIGH half, so the second 32-bit draw is the high one."""
    generator = np.random.default_rng(VECTOR_SEEDS[0])
    raw = int(np.random.default_rng(VECTOR_SEEDS[0]).bit_generator.random_raw())
    first = int(generator.integers(0, 2**32, dtype=np.uint32))
    state = generator.bit_generator.state
    assert first == raw & 0xFFFFFFFF, "the first 32-bit draw is the low half of one 64-bit word"
    assert state["has_uint32"] == 1, "the high half must be buffered, not discarded"
    assert state["uinteger"] == raw >> 32
    second = int(generator.integers(0, 2**32, dtype=np.uint32))
    assert second == raw >> 32, "the buffered high half must be the next 32-bit draw"
    assert generator.bit_generator.state["has_uint32"] == 0


def test_the_mixed_program_actually_exercises_the_buffer() -> None:
    """A vector file that never fills the buffer would let a wrong port pass."""
    rows = mixed_rows(VECTOR_SEEDS[0])
    assert len(rows) == len(MIXED_PROGRAM)
    assert any(row["has_uint32"] == 1 for row in rows), "the buffer is never filled"
    assert any(row["has_uint32"] == 0 for row in rows), "the buffer is never drained"
    assert {row["op"] for row in rows} == set(NARROW_OPS) | set(WIDE_OPS)
    # A 64-bit draw must not disturb a filled buffer; a 32-bit one must spend it. Both halves, because
    # a port can get either wrong and each produces a different family of wrong numbers.
    for before, after in itertools.pairwise(rows):
        if before["has_uint32"] != 1:
            continue
        if after["op"] in WIDE_OPS:
            assert after["has_uint32"] == 1, f"{after['op']} drained the 32-bit buffer"
            assert after["uinteger"] == before["uinteger"]
        else:
            assert after["has_uint32"] == 0, f"{after['op']} did not spend the buffered half"


def test_integers_and_choice_read_the_32_bit_generator_whatever_the_dtype_says() -> None:
    """Measured, and load-bearing: `integers(0, len(targets))` picks every exercise's label.

    A range that fits in 32 bits goes through `next_uint32` even when the dtype is int64, so the draw
    comes out of the buffered half of a 64-bit word. A port reading it from `next_uint64` produces
    correct chart noise and the wrong label on every seed.
    """
    def buffer_after(call: Any) -> tuple[int, bool]:
        generator = np.random.default_rng(VECTOR_SEEDS[0])
        generator.integers(0, 10, dtype=np.uint32)  # fill the buffer
        before = generator.bit_generator.state
        assert before["has_uint32"] == 1
        call(generator)
        after = generator.bit_generator.state
        return int(after["has_uint32"]), after["state"]["state"] != before["state"]["state"]

    for call in (
        lambda g: g.integers(0, 10),
        lambda g: g.integers(0, 2**32),
        lambda g: g.choice(np.arange(5)),
    ):
        assert buffer_after(call) == (0, False), "expected a 32-bit consumer"
    for call in (
        lambda g: g.integers(0, 2**32 + 1),
        lambda g: g.random(),
        lambda g: g.uniform(0.0, 1.0),
        lambda g: g.standard_normal(),
        lambda g: g.bit_generator.random_raw(),
    ):
        assert buffer_after(call) == (1, True), "expected a 64-bit consumer"


def test_the_ziggurat_path_is_identified_by_the_words_consumed_and_the_value() -> None:
    """The instrument's own contract: |x| > r iff the accept came from the tail, and the tail costs
    more than one 64-bit word — so a `fast` row can never be a tail value."""
    seen = {"fast": 0, "wedge": 0, "tail": 0}
    for seed in VECTOR_SEEDS:
        for row in normal_rows(seed):
            seen[row["path"]] += 1
            value = abs(float(row["value"]))
            if row["path"] == "fast":
                assert row["words"] == 1, row
                assert value <= ZIGGURAT_NOR_R, row
            else:
                assert row["words"] >= 2, row
            if value > ZIGGURAT_NOR_R:
                assert row["path"] == "tail", row
            elif row["words"] > 1:
                assert row["path"] == "wedge", row
    assert seen["fast"] > 0 and seen["wedge"] > 0
    assert seen["tail"] > 0, (
        "no exported seed enters the ziggurat tail, so the README's tail-seed list would be empty "
        "and the one path where two correct libms differ would be unpinned"
    )


def test_the_normal_rows_reproduce_the_draw_they_record() -> None:
    """The hex is the value: a port comparing decimal text would compare a rounding, not a double."""
    rows = normal_rows(VECTOR_SEEDS[1])
    assert len(rows) == DRAWS_PER_SEED
    expected = np.random.default_rng(VECTOR_SEEDS[1]).standard_normal(DRAWS_PER_SEED)
    for row, value in zip(rows, expected.tolist(), strict=True):
        assert float(row["value"]) == value
        assert row["hex"] == "0x" + np.float64(value).tobytes()[::-1].hex()


def test_the_quiz_layout_vectors_come_from_the_generator_itself() -> None:
    """Reused, not re-derived: these rows must be `quiz._shuffled`'s own output for the real salts."""
    from tradeschool.exercises.quiz import _shuffled

    rows = quiz_layout_rows()
    assert rows, "no quiz layout vectors"
    for row in rows:
        assert row["order"] == _shuffled(row["n"], row["seed"], row["salt"]), row
    salts = {row["salt"] for row in rows}
    assert {0, 1, 2}.issubset(salts), f"the matching salts are missing: {sorted(salts)}"


def test_the_cpython_state_is_the_seeded_mersenne_twister() -> None:
    """`init_by_array` is the fiddly half of a Mersenne Twister port, so the seeded state is pinned."""
    for seed in VECTOR_SEEDS[:4]:
        exported = cpython_mt_state(seed)
        version, state, gauss = random.Random(seed).getstate()
        assert version == 3
        assert gauss is None
        assert exported["words"] == list(state[:-1])
        assert exported["index"] == state[-1]
        assert len(exported["words"]) == 624


def test_every_vector_file_is_deterministic_and_covers_enough_seeds() -> None:
    assert len(set(VECTOR_SEEDS)) == len(VECTOR_SEEDS)
    assert len(VECTOR_SEEDS) >= 10, "the contract asks for at least ten distinct seeds"
    assert DRAWS_PER_SEED >= 1000, "the contract asks for at least a thousand draws per primitive"
    first, second = build_all(), build_all()
    assert set(first) == set(second)
    for name in first:
        assert first[name] == second[name], f"{name} is not reproducible"


@pytest.mark.parametrize("name", ["seedsequence", "pcg64-raw", "pcg64-normal", "cpython-random"])
def test_the_headline_files_are_written_with_a_column_header(name: str) -> None:
    body = build_all()[name]
    lines = [line for line in body.splitlines() if not line.startswith("#")]
    assert lines, name
    assert "\t" in lines[0], f"{name}: the first non-comment line must be the column header"
    columns = lines[0].split("\t")
    for line in lines[1:]:
        assert len(line.split("\t")) == len(columns), f"{name}: ragged row {line[:60]!r}"
