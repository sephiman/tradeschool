# SPDX-License-Identifier: AGPL-3.0-only
"""Write `dist/contracts/prng-vectors/` — the random streams the Kotlin port has to reproduce exactly.

Phase W2. Everything downstream of this is pointless if the two languages disagree here: a chart is a
walk of Gaussian draws, an option list is a shuffle, and a single wrong bit in either makes every
cross-language golden fail with no information about why. So the port gets vectors first, per
primitive, and debugs against them rather than against a whole chart.

TWO generators, and they are unrelated. The charts use NumPy's `default_rng(seed)`, i.e. PCG64 seeded
through a SeedSequence. The exercise machinery uses CPython's `random.Random(seed)`, i.e. a Mersenne
Twister seeded through `init_by_array`. Both are exported, because both decide something a learner sees.

The three subtleties the vectors exist to pin, all of them silent when got wrong:

  * **Seeding.** `default_rng(seed)` is not "PCG64 with state = seed". It is `SeedSequence(seed)`
    expanded to four 64-bit words, which then go through `pcg64_srandom_r` — two LCG steps around an
    addition. `seedsequence.tsv` carries the words AND the resulting `(state, inc)` pair, so a port
    can check the expansion and the seeding separately instead of guessing which half is wrong.
  * **The 32-bit buffer.** `next_uint32` takes one 64-bit draw and hands out its LOW half, keeping
    the high half in `uinteger` for the next call; a 64-bit draw in between does not disturb it.
    `pcg64-mixed.tsv` interleaves the two widths and records the buffer after every operation.
  * **The ziggurat tail.** `normal()` returns from a table 99% of the time, from an `exp`-guarded
    wedge test sometimes, and from a `log`-based tail rarely. Only the last two call libm, and libm
    is the one place two correct implementations may legitimately differ by an ulp — so the vectors
    say, per draw, which path produced it, and the README lists the seeds that reach the tail.

Which path a draw took is not visible in its value alone, so it is measured: the instrument counts the
64-bit words the draw consumed (one = a table hit, more = at least one libm-bearing test) and reads
the value against `ZIGGURAT_NOR_R` (above it = the accept came from the tail). Production code is
untouched; the counting is done by replaying the bit generator's own state.

The tail vectors are INFORMATIVE, deliberately. The binding cross-language contract is the rounded
payload (`export_generation_goldens.py`), because that is what a reader sees and what the committed
fingerprints hash; raw ziggurat doubles are where a 1-ulp libm difference is allowed to show up. See
`phase-w1-numeric-sanitization.md` §3 for why that line is drawn there.

Usage (from `backend/`):
    uv run python scripts/export_prng_vectors.py
    uv run python scripts/export_prng_vectors.py --out ../dist/contracts/prng-vectors
"""

from __future__ import annotations

import argparse
import platform
import random
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

_BACKEND = Path(__file__).resolve().parent.parent
for _extra in (_BACKEND, _BACKEND / "src"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from scripts.measure_libm_parity import hex64  # noqa: E402  the one definition of a double's bits
from tradeschool.content.print_export import print_seed  # noqa: E402
from tradeschool.exercises.quiz import _shuffled  # noqa: E402

DEFAULT_OUT = _BACKEND.parent / "dist" / "contracts" / "prng-vectors"

#: PCG64's LCG multiplier, as `pcg64_next64` uses it (a 128-bit constant, high 64 bits first).
PCG64_MULTIPLIER = (2549297995355413924 << 64) | 4865540595714422341
_MASK128 = (1 << 128) - 1

#: The ziggurat's tail boundary, from NumPy's `distributions.c`. Every |x| above it was produced by
#: the tail branch and nothing else can produce one, which is what makes the path observable.
ZIGGURAT_NOR_R = 3.6541528853610088

#: Draws per seed for the single-parameter primitives. The contract asks for a thousand minimum.
DRAWS_PER_SEED = 1000

#: Draws per (seed, parameter) for the families that take bounds — with the seed list below that is
#: well past a thousand draws per primitive while keeping each file readable.
DRAWS_PER_PARAM = 64

#: The seeds. Small integers because that is what the figures and the probe sweeps use; the two large
#: ones because `print_seed` lives in a 62-bit space and an attempt's seed is an arbitrary integer —
#: a port whose SeedSequence only handles small entropy would pass everything else and fail the book.
VECTOR_SEEDS: tuple[int, ...] = (
    0, 1, 2, 3, 4, 5, 8, 11, 12, 13, 16, 20, 21, 24,
    print_seed("m01-ex-1"),
    print_seed("m30-ex-3"),
)

#: `rng.integers(low, high)` as the generation path calls it — regime counts, coin flips, and the
#: label lottery, whose upper bound is the length of a config's `targets` list.
INTEGER_BOUNDS: tuple[tuple[int, int], ...] = (
    (0, 2), (0, 3), (0, 5), (0, 6), (0, 9), (0, 15), (2, 4), (2, 5), (0, 2**63 - 1),
)

#: `rng.uniform(low, high)` bounds spanning the real call sites: drift regimes, volatility
#: multipliers, base-price jitter and leg lengths.
UNIFORM_BOUNDS: tuple[tuple[float, float], ...] = (
    (0.0, 1.0), (-0.0006, 0.0006), (0.0025, 0.006), (0.085, 0.155), (0.6, 1.8), (0.9, 1.1),
)

#: `rng.choice(a)` population sizes: 2 (the sign coin), 5 (`injectors._BASE_PRICES`) and the label
#: list lengths an injector offers. Exported as a choice over `arange(n)`, so the value IS the index
#: a port has to reproduce.
CHOICE_SIZES: tuple[int, ...] = (2, 3, 5, 6, 9, 15)

#: Which PCG64 entry point each mixed operation goes through — MEASURED, not assumed, and the
#: surprise of this whole file. `Generator.integers` uses the 32-BIT generator whenever the requested
#: range fits in 32 bits, whatever dtype was asked for, and `choice` is `integers` underneath. So the
#: label lottery (`rng.integers(0, len(targets))`) and the base-price pick (`rng.choice(...)`) are
#: 32-bit consumers, and a port that routes them through `next_uint64` gets a different label and a
#: different price for every seed while every chart's noise still matches.
NARROW_OPS = ("u32", "i32", "i64small", "f32", "choice5")
WIDE_OPS = ("raw64", "f64", "i64wide", "normal")

#: One operation per row of `pcg64-mixed-32-64.tsv`. The pattern is deliberate rather than random: a
#: 32-bit draw right after a 64-bit one, two 32-bit draws in a row (the second must come out of the
#: buffer), a 64-bit draw across a FILLED buffer (which must leave it filled), and the two integer
#: widths side by side.
MIXED_PROGRAM: tuple[str, ...] = (
    ("raw64", "u32", "u32", "raw64", "u32", "f64", "u32", "u32", "u32", "i64small", "i64wide",
     "u32", "f32", "f32", "raw64", "u32", "f32", "i32", "i32", "normal", "u32", "choice5",
     "i64wide", "u32", "f64", "u32", "i64small", "choice5", "raw64", "u32")
    * 2
)

#: `(n, salt)` pairs for the CPython shuffles the exercise machinery actually performs: salt 0 lays
#: out a single/multi-select option list or an ordering, salts 1 and 2 lay out the two columns of a
#: `matching` question, and 7 is the calculation option order (`seed * 1000 + 7`).
QUIZ_LAYOUTS: tuple[tuple[int, int], ...] = (
    (2, 0), (3, 0), (4, 0), (5, 0), (6, 0),
    (3, 1), (3, 2), (4, 1), (4, 2), (5, 1), (5, 2), (6, 1), (6, 2),
    (4, 7),
)


# --- NumPy: seeding --------------------------------------------------------------------------------


def seed_state_words(seed: int, *, count: int, bits: int = 64) -> list[int]:
    """`SeedSequence(seed)` expanded to `count` words — the exact expansion `default_rng` performs."""
    dtype = np.uint64 if bits == 64 else np.uint32
    return [int(word) for word in np.random.SeedSequence(seed).generate_state(count, dtype=dtype)]


def pcg64_state_from_words(words: list[int]) -> dict[str, int]:
    """The four expanded words turned into PCG64's `(state, inc)` by `pcg64_srandom_r`.

    Written out in Python arithmetic rather than read off the bit generator, because this IS the
    contract: a port has these four words and needs to know exactly what to do with them.
    """
    initstate = (words[0] << 64) | words[1]
    # `& _MASK128` is not decoration: `initseq << 1` overflows 128 bits whenever `words[2]`
    # has its top bit set, which is half of all seeds.
    inc = ((((words[2] << 64) | words[3]) << 1) | 1) & _MASK128
    state = 0
    state = (state * PCG64_MULTIPLIER + inc) & _MASK128
    state = (state + initstate) & _MASK128
    state = (state * PCG64_MULTIPLIER + inc) & _MASK128
    return {"state": state, "inc": inc}


def _spawn_keys(seed: int, children: int) -> list[list[int]]:
    """`SeedSequence.spawn` keys. No injector spawns today; exported so a future one is already pinned."""
    return [list(child.spawn_key) for child in np.random.SeedSequence(seed).spawn(children)]


# --- NumPy: the streams ----------------------------------------------------------------------------


def raw_rows(seed: int) -> list[dict[str, Any]]:
    generator = np.random.default_rng(seed)
    return [
        {"index": index, "raw64": int(value)}
        for index, value in enumerate(generator.bit_generator.random_raw(DRAWS_PER_SEED).tolist())
    ]


def double_rows(seed: int) -> list[dict[str, Any]]:
    values = np.random.default_rng(seed).random(DRAWS_PER_SEED)
    return [
        {"index": index, "hex": hex64(value), "value": repr(value)}
        for index, value in enumerate(values.tolist())
    ]


def integer_rows(seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for low, high in INTEGER_BOUNDS:
        generator = np.random.default_rng(seed)
        drawn = generator.integers(low, high, DRAWS_PER_PARAM)
        rows.extend(
            {"low": low, "high": high, "index": index, "value": int(value)}
            for index, value in enumerate(drawn.tolist())
        )
    return rows


def uniform_rows(seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for low, high in UNIFORM_BOUNDS:
        generator = np.random.default_rng(seed)
        drawn = generator.uniform(low, high, DRAWS_PER_PARAM)
        rows.extend(
            {"low": hex64(low), "high": hex64(high), "index": index, "hex": hex64(value)}
            for index, value in enumerate(drawn.tolist())
        )
    return rows


def choice_rows(seed: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for size in CHOICE_SIZES:
        generator = np.random.default_rng(seed)
        population = np.arange(size)
        rows.extend(
            {"n": size, "index": index, "chosen": int(generator.choice(population))}
            for index in range(DRAWS_PER_PARAM)
        )
    return rows


def shuffle_rows(seed: int) -> list[dict[str, Any]]:
    """NumPy `shuffle`, which NO injector uses today — see the README's note before porting against it."""
    rows: list[dict[str, Any]] = []
    for size in CHOICE_SIZES:
        generator = np.random.default_rng(seed)
        for index in range(DRAWS_PER_PARAM):
            order = np.arange(size)
            generator.shuffle(order)
            rows.append({"n": size, "index": index, "order": ",".join(str(v) for v in order.tolist())})
    return rows


def _words_consumed(before: Mapping[str, Any], after: Mapping[str, Any], limit: int = 64) -> int:
    """How many 64-bit words one call took, by replaying the bit generator from its own prior state."""
    replay = np.random.PCG64()
    replay.state = dict(before)  # type: ignore[assignment]  # the setter takes the state mapping back
    for steps in range(1, limit + 1):
        replay.random_raw()
        if dict(replay.state)["state"] == after["state"]:
            return steps
    raise RuntimeError("the bit generator advanced further than a single draw plausibly could")


def normal_rows(seed: int) -> list[dict[str, Any]]:
    """One standard-normal draw per row, with the ziggurat path that produced it.

    Drawn one at a time on purpose: the state before and after each draw is what makes the path
    observable, and a vectorized call would collapse a thousand draws into one state transition.
    """
    generator = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for index in range(DRAWS_PER_SEED):
        before = dict(generator.bit_generator.state)
        value = float(generator.standard_normal())
        words = _words_consumed(before, dict(generator.bit_generator.state))
        if words == 1:
            path = "fast"
        elif abs(value) > ZIGGURAT_NOR_R:
            path = "tail"
        else:
            path = "wedge"
        rows.append(
            {"index": index, "hex": hex64(value), "value": repr(value), "words": words, "path": path}
        )
    return rows


def mixed_rows(seed: int) -> list[dict[str, Any]]:
    """The interleaved 32/64-bit program, with the buffer's state recorded after every operation."""
    generator = np.random.default_rng(seed)
    rows: list[dict[str, Any]] = []
    for index, op in enumerate(MIXED_PROGRAM):
        if op == "raw64":
            value = str(int(generator.bit_generator.random_raw()))
        elif op == "u32":
            value = str(int(generator.integers(0, 2**32, dtype=np.uint32)))
        elif op == "i32":
            value = str(int(generator.integers(0, 10, dtype=np.uint32)))
        elif op == "i64small":
            value = str(int(generator.integers(0, 10)))
        elif op == "i64wide":
            value = str(int(generator.integers(0, 2**40)))
        elif op == "choice5":
            value = str(int(generator.choice(np.arange(5))))
        elif op == "f64":
            value = hex64(float(generator.random()))
        elif op == "f32":
            value = "0x" + np.float32(generator.random(dtype=np.float32)).tobytes()[::-1].hex()
        elif op == "normal":
            value = hex64(float(generator.standard_normal()))
        else:  # pragma: no cover - MIXED_PROGRAM is a closed list
            raise ValueError(f"unknown mixed operation {op!r}")
        state = generator.bit_generator.state
        rows.append(
            {
                "index": index,
                "op": op,
                "width": "32" if op in NARROW_OPS else "64",
                "value": value,
                "has_uint32": int(state["has_uint32"]),
                "uinteger": int(state["uinteger"]),
            }
        )
    return rows


# --- CPython's Mersenne Twister --------------------------------------------------------------------


def cpython_mt_state(seed: int) -> dict[str, Any]:
    """The 624 state words after `init_by_array`, plus the index — the seeding a port must reproduce."""
    _version, state, _gauss = random.Random(seed).getstate()
    return {"words": list(state[:-1]), "index": state[-1]}


def cpython_rows(seed: int) -> list[dict[str, Any]]:
    """One row per primitive call, in a fixed program, one generator per FAMILY.

    A fresh `random.Random(seed)` per (primitive, arg) family, because a port debugging `getrandbits`
    should not have to reproduce `random()` first to get to it — and then that ONE generator advances
    across the family's rows.

    Both halves are load-bearing, and the second was once wrong: the `random` family built its
    generator inside the loop, so every row held draw 0 and 15,984 of 16,000 exported rows described
    no CPython behaviour at all. It survived because nothing asserted that a column advances.
    `test_every_cpython_family_reproduces_one_sequential_generator` now does, for every family.
    """
    rows: list[dict[str, Any]] = []
    generator = random.Random(seed)
    for index in range(DRAWS_PER_SEED):
        rows.append(
            {"primitive": "random", "arg": "", "index": index, "value": hex64(generator.random())}
        )
    for bits in (1, 4, 15, 16, 31, 32, 53, 64):
        generator = random.Random(seed)
        for index in range(DRAWS_PER_PARAM):
            rows.append(
                {
                    "primitive": "getrandbits",
                    "arg": str(bits),
                    "index": index,
                    "value": str(generator.getrandbits(bits)),
                }
            )
    for bound in (2, 3, 4, 5, 6, 9, 15, 147):
        generator = random.Random(seed)
        for index in range(DRAWS_PER_PARAM):
            rows.append(
                {
                    "primitive": "_randbelow",
                    "arg": str(bound),
                    "index": index,
                    # `shuffle` and `choice` are both defined in terms of this, so it is the primitive
                    # a port must match; the two below are then arithmetic on top of it.
                    # `_randbelow` is private and deliberately reached for: it is the primitive,
                    # and a port that matches `shuffle` by accident while getting this wrong will
                    # diverge the moment a list length changes.
                    "value": str(generator._randbelow(bound)),  # type: ignore[attr-defined]
                }
            )
    for size in (2, 3, 5, 6, 9, 15):
        generator = random.Random(seed)
        population = list(range(size))
        for index in range(DRAWS_PER_PARAM):
            rows.append(
                {
                    "primitive": "choice",
                    "arg": str(size),
                    "index": index,
                    "value": str(generator.choice(population)),
                }
            )
    for size in (2, 3, 5, 6, 9, 15):
        generator = random.Random(seed)
        for index in range(DRAWS_PER_PARAM):
            order = list(range(size))
            generator.shuffle(order)
            rows.append(
                {
                    "primitive": "shuffle",
                    "arg": str(size),
                    "index": index,
                    "value": ",".join(str(v) for v in order),
                }
            )
    for low, high in ((0, 1), (0, 9), (1, 6), (0, 146)):
        generator = random.Random(seed)
        for index in range(DRAWS_PER_PARAM):
            rows.append(
                {
                    "primitive": "randint",
                    "arg": f"{low},{high}",
                    "index": index,
                    "value": str(generator.randint(low, high)),
                }
            )
    for bound in (2, 5, 18, 147):
        generator = random.Random(seed)
        for index in range(DRAWS_PER_PARAM):
            rows.append(
                {
                    "primitive": "randrange",
                    "arg": str(bound),
                    "index": index,
                    "value": str(generator.randrange(bound)),
                }
            )
    return rows


def quiz_layout_rows() -> list[dict[str, Any]]:
    """`quiz._shuffled(n, seed, salt)` — the generator's own function, never a copy of its arithmetic."""
    return [
        {"n": n, "seed": seed, "salt": salt, "derived_seed": seed * 1000 + salt,
         "order": _shuffled(n, seed, salt)}
        for n, salt in QUIZ_LAYOUTS
        for seed in VECTOR_SEEDS
    ]


# --- files -----------------------------------------------------------------------------------------


def _seedsequence_row(seed: int) -> list[str]:
    """One seed's whole expansion, computed once — the wide words, the state they seed, the narrow view."""
    wide = seed_state_words(seed, count=4)
    state = pcg64_state_from_words(wide)
    return [
        str(seed),
        *[str(word) for word in wide],
        str(state["state"]),
        str(state["inc"]),
        ",".join(str(word) for word in seed_state_words(seed, count=8, bits=32)),
        ";".join(",".join(str(key) for key in child) for child in _spawn_keys(seed, 2)),
    ]


def _tsv(header: str, comment: list[str], rows: list[list[str]]) -> str:
    body = ["# " + line if line else "#" for line in comment]
    body.append(header)
    body.extend("\t".join(row) for row in rows)
    return "\n".join(body) + "\n"


def _seed_note(kind: str) -> list[str]:
    return [
        f"{kind}, one row per draw.",
        "",
        f"seeds: {len(VECTOR_SEEDS)} — {', '.join(str(s) for s in VECTOR_SEEDS)}",
        "Doubles are the exact IEEE-754 bit pattern (`0x` + 16 hex digits, big-endian); integers are",
        "decimal. A port comparing decimal text for a double compares a rounding, not the value.",
    ]


def build_all() -> dict[str, str]:
    """Every vector file's body, by name. Pure: the same input always gives the same bytes."""
    files: dict[str, str] = {}

    files["seedsequence"] = _tsv(
        "seed\tw64_0\tw64_1\tw64_2\tw64_3\tpcg64_state\tpcg64_inc\tw32_0..7\tspawn_keys",
        [
            "SeedSequence expansion and the PCG64 state it seeds — `np.random.default_rng(seed)`.",
            "",
            "`w64_*` is `SeedSequence(seed).generate_state(4, uint64)`, in order. `pcg64_state` and",
            "`pcg64_inc` are what `pcg64_srandom_r` makes of them:",
            "    inc   = (((w64_2 << 64 | w64_3) << 1) | 1) mod 2^128",
            "    state = 0",
            "    state = state * MULT + inc          (mod 2^128)",
            "    state = state + (w64_0 << 64 | w64_1)",
            "    state = state * MULT + inc",
            f"with MULT = {PCG64_MULTIPLIER} (0x2360ED051FC65DA44385DF649FCCF645).",
            "",
            "`w32_0..7` is the SAME expansion asked for 8 uint32 words: each 64-bit word split",
            "little-endian (low half first), NOT a second stream.",
            "",
            "`spawn_keys` are `SeedSequence(seed).spawn(2)`'s keys. INFORMATIVE: no injector spawns",
            "today, so a port needs this only if one ever does.",
        ],
        [_seedsequence_row(seed) for seed in VECTOR_SEEDS],
    )

    files["pcg64-raw"] = _tsv(
        "seed\tindex\traw64",
        [
            *_seed_note("PCG64 raw 64-bit output (`bit_generator.random_raw`)"),
            "",
            f"{DRAWS_PER_SEED} draws per seed.",
        ],
        [[str(seed), str(row["index"]), str(row["raw64"])]
         for seed in VECTOR_SEEDS for row in raw_rows(seed)],
    )

    files["pcg64-double"] = _tsv(
        "seed\tindex\thex\tdecimal",
        [
            *_seed_note("`Generator.random()` — `(next_uint64() >> 11) * 2^-53`"),
            "",
            f"{DRAWS_PER_SEED} draws per seed.",
        ],
        [[str(seed), str(row["index"]), row["hex"], row["value"]]
         for seed in VECTOR_SEEDS for row in double_rows(seed)],
    )

    files["pcg64-integers"] = _tsv(
        "seed\tlow\thigh\tindex\tvalue",
        [
            *_seed_note("`Generator.integers(low, high)` — half-open, the bounds the injectors use"),

            "",
            f"{DRAWS_PER_PARAM} draws per (seed, bounds); each bound restarts from the seed.",
            "`(0, 2**63-1)` is here to exercise the wide path; the rest are real call sites, and",
            "`(0, len(targets))` is the label lottery whose bound is a config's own list length.",
        ],
        [[str(seed), str(row["low"]), str(row["high"]), str(row["index"]), str(row["value"])]
         for seed in VECTOR_SEEDS for row in integer_rows(seed)],
    )

    files["pcg64-uniform"] = _tsv(
        "seed\tlow_hex\thigh_hex\tindex\thex",
        [
            *_seed_note("`Generator.uniform(low, high)`"),
            "",
            f"{DRAWS_PER_PARAM} draws per (seed, bounds); each bound restarts from the seed.",
        ],
        [[str(seed), row["low"], row["high"], str(row["index"]), row["hex"]]
         for seed in VECTOR_SEEDS for row in uniform_rows(seed)],
    )

    files["pcg64-normal"] = _tsv(
        "seed\tindex\thex\tdecimal\twords\tpath",
        [
            *_seed_note("`Generator.standard_normal()` — the 256-level ziggurat"),

            "",
            f"{DRAWS_PER_SEED} draws per seed, drawn ONE AT A TIME so each draw's cost is visible.",
            "`words` is how many 64-bit words the draw consumed; `path` is where it came from:",
            "    fast   one word, a table hit — no libm call at all",
            "    wedge  more than one word, |x| <= r — an `exp` guard ran",
            f"    tail   |x| > r = {ZIGGURAT_NOR_R!r} — the `log`-based tail produced it",
            "Only `wedge` and `tail` rows can differ between two correct libms, and then by an ulp.",
            "They are INFORMATIVE: the binding contract is the rounded payload, not these doubles.",
        ],
        [[str(seed), str(row["index"]), row["hex"], row["value"], str(row["words"]), row["path"]]
         for seed in VECTOR_SEEDS for row in normal_rows(seed)],
    )

    files["pcg64-mixed-32-64"] = _tsv(
        "seed\tindex\top\twidth\tvalue\thas_uint32\tuinteger",
        [
            "Interleaved 32- and 64-bit draws, with the 32-bit buffer's state after every operation.",
            "",
            "`next_uint32` takes ONE 64-bit draw and returns its LOW half, keeping the high half in",
            "`uinteger` with `has_uint32 = 1`; the next 32-bit draw returns that buffered half and",
            "clears the flag. A 64-bit draw in between does NOT disturb the buffer. A port that",
            "returns the high half first, or that drops the buffer on a 64-bit draw, produces correct",
            "64-bit values and wrong 32-bit ones — which is why the buffer is a column here.",
            "",
            "`width` says which entry point the operation goes through, and it is MEASURED rather",
            "than inferred from the dtype. `Generator.integers` uses the 32-BIT generator whenever the",
            "requested range fits in 32 bits, whatever dtype was asked for, and `choice` is `integers`",
            "underneath — so `i64small` and `choice5` are 32-bit consumers while `i64wide` is not.",
            "That is the one line of this file the generation path depends on: `rng.integers(0,",
            "len(targets))` picks every exercise's label, and `rng.choice(_BASE_PRICES)` picks every",
            "chart's price level.",
            "",
            "ops:  raw64    = bit_generator.random_raw()            (64)",
            "      f64      = random()                              (64)",
            "      normal   = standard_normal()                     (64)",
            "      i64wide  = integers(0, 2**40)                    (64)",
            "      u32      = integers(0, 2**32, dtype=uint32)      (32)",
            "      i32      = integers(0, 10, dtype=uint32)         (32)",
            "      i64small = integers(0, 10)                       (32, despite the int64 dtype)",
            "      choice5  = choice(arange(5))                     (32, it is `integers` inside)",
            "      f32      = random(dtype=float32)                 (32)",
            "",
            "`value` is decimal for integers and a bit pattern for floats (16 hex digits for a double,",
            "8 for a float32).",
        ],
        [[str(seed), str(row["index"]), row["op"], row["width"], row["value"],
          str(row["has_uint32"]), str(row["uinteger"])]
         for seed in VECTOR_SEEDS for row in mixed_rows(seed)],
    )

    files["pcg64-choice"] = _tsv(
        "seed\tn\tindex\tchosen",
        [
            *_seed_note(
                "`Generator.choice(arange(n))` as the injectors call it — one element, with replacement"
            ),

            "",
            "The population is `arange(n)`, so the VALUE is the index `choice` picked: that is the",
            "number a port has to reproduce, whatever the real population happens to hold.",
            "n covers the real ones: 2 (the sign coin), 5 (`injectors._BASE_PRICES`) and the label",
            "list lengths an injector offers.",
        ],
        [[str(seed), str(row["n"]), str(row["index"]), str(row["chosen"])]
         for seed in VECTOR_SEEDS for row in choice_rows(seed)],
    )

    files["pcg64-shuffle"] = _tsv(
        "seed\tn\tindex\torder",
        [
            "`Generator.shuffle(arange(n))` — a Fisher-Yates in NumPy's own direction.",
            "",
            "NOT USED BY ANY INJECTOR TODAY. Every shuffle a learner sees is CPython's (see",
            "`cpython-random.tsv`, primitive `shuffle`). Exported so that a future NumPy-side shuffle",
            "is already pinned rather than introduced unpinned — do not port against this file",
            "expecting it to explain an option order.",
        ],
        [[str(seed), str(row["n"]), str(row["index"]), row["order"]]
         for seed in VECTOR_SEEDS for row in shuffle_rows(seed)],
    )

    files["cpython-mt-state"] = _tsv(
        "seed\tindex\tword",
        [
            "CPython `random.Random(seed)`'s Mersenne Twister state right after seeding.",
            "",
            "`random_seed` converts the integer seed to an array of 32-bit words (little-endian, the",
            "absolute value) and runs `init_by_array` — not `init_genrand`. That distinction is the",
            "usual first bug in a port, and it is invisible until a whole shuffle comes out wrong.",
            "624 words per seed, plus `index` 624 (meaning `genrand` will twist on its next call).",
        ],
        [[str(seed), str(index), str(word)]
         for seed in VECTOR_SEEDS
         for index, word in enumerate([*cpython_mt_state(seed)["words"], cpython_mt_state(seed)["index"]])],
    )

    files["cpython-random"] = _tsv(
        "seed\tprimitive\targ\tindex\tvalue",
        [
            "CPython `random.Random(seed)` — the primitives the exercise machinery consumes.",
            "",
            "Each (primitive, arg) family restarts from a FRESH `Random(seed)`, so a port can debug",
            "one primitive without first reproducing the others.",
            "",
            "  random       a 53-bit double: `(genrand>>5) * 2**26 + (genrand>>6)) * 2**-53`,",
            f"               {DRAWS_PER_SEED} draws, as a bit pattern",
            "  getrandbits  `arg` bits; over 32 bits it is assembled from several 32-bit words",
            "  _randbelow   the private uniform-below-n every shuffle and choice is built on:",
            "               `getrandbits(n.bit_length())` with rejection until the value is < n",
            "  choice       `seq[_randbelow(len(seq))]` over `range(arg)`",
            "  shuffle      `range(arg)` shuffled, comma-separated: the DOWNWARD Fisher-Yates",
            "               (`for i in reversed(range(1, n)): swap(i, _randbelow(i + 1))`)",
            "  randint      `randrange(a, b+1)` over `arg = a,b`",
            "  randrange    `randrange(arg)`",
            "",
            f"seeds: {', '.join(str(s) for s in VECTOR_SEEDS)}",
        ],
        [[str(seed), row["primitive"], row["arg"], str(row["index"]), row["value"]]
         for seed in VECTOR_SEEDS for row in cpython_rows(seed)],
    )

    files["quiz-layout"] = _tsv(
        "n\tsalt\tseed\tderived_seed\torder",
        [
            "The option/item/pair orders the quiz and calculation generators actually lay out.",
            "",
            "`quiz._shuffled(n, seed, salt)` is `Random(seed * 1000 + salt).shuffle(range(n))`, and",
            "the salt is what keeps one instance's several shuffles independent:",
            "    0  a single_choice / multi_select option list, or an `ordering`'s items",
            "    1  a `matching` question's LEFT column",
            "    2  the same question's RIGHT column — a different salt, or the two columns would",
            "       be permuted identically and every pair would sit on its own row",
            "    7  the calculation option order (`_mc_options` uses `seed * 1000 + 7`)",
            "",
            "`order` is the permutation of `range(n)`: slot i shows the original item `order[i]`.",
        ],
        [[str(row["n"]), str(row["salt"]), str(row["seed"]), str(row["derived_seed"]),
          ",".join(str(v) for v in row["order"])]
         for row in quiz_layout_rows()],
    )

    return files


def tail_seed_summary() -> list[tuple[int, int, int, int]]:
    """`(seed, fast, wedge, tail)` per seed — what the README's tail list is built from."""
    summary: list[tuple[int, int, int, int]] = []
    for seed in VECTOR_SEEDS:
        counts = {"fast": 0, "wedge": 0, "tail": 0}
        for row in normal_rows(seed):
            counts[row["path"]] += 1
        summary.append((seed, counts["fast"], counts["wedge"], counts["tail"]))
    return summary


def readme_text(files: dict[str, str], summary: list[tuple[int, int, int, int]]) -> str:
    tail_seeds = [seed for seed, _fast, _wedge, tail in summary if tail > 0]
    lines = [
        "<!-- SPDX-License-Identifier: AGPL-3.0-only -->",
        "# PRNG contract vectors",
        "",
        "Generated by `backend/scripts/export_prng_vectors.py` in the TradeSchool web repository.",
        "Do not hand-edit: regenerate, and read the diff.",
        "",
        "Every chart and every shuffled option list in this course is a function of a seed, and the",
        "Android port reproduces the generators rather than calling a server. These files are what it",
        "is verified against, primitive by primitive, so a divergence is localized to one draw instead",
        "of showing up as a whole chart that does not match.",
        "",
        "## Two generators, and they are unrelated",
        "",
        "| | used for | seeded by |",
        "| --- | --- | --- |",
        "| **NumPy PCG64** (`np.random.default_rng`) | every chart: prices, wicks, volume, noise |"
        " `SeedSequence` -> 4 words -> `pcg64_srandom_r` |",
        "| **CPython Mersenne Twister** (`random.Random`) | option order, variant choice, matching"
        " columns, calculation parameters | `init_by_array` over the seed's 32-bit words |",
        "",
        "## File format",
        "",
        "Every file is a TSV. Lines starting with `#` are a header explaining that file; the first",
        "line that does not is the **column header**; every line after it is a row. Doubles are the",
        "exact IEEE-754 bit pattern as `0x` + 16 hex digits, big-endian (`0x` + 8 for a float32);",
        "integers are decimal. Nothing is rounded anywhere: a port that compares printed decimals is",
        "comparing roundings, and two libms may agree on the double and disagree on its 17th digit.",
        "",
        "## The files",
        "",
        "| file | primitive | rows |",
        "| --- | --- | --- |",
    ]
    descriptions = {
        "seedsequence": "SeedSequence expansion + the PCG64 state it seeds",
        "pcg64-raw": "raw 64-bit output",
        "pcg64-double": "`random()`",
        "pcg64-integers": "`integers(low, high)`",
        "pcg64-uniform": "`uniform(low, high)`",
        "pcg64-normal": "`standard_normal()`, with the ziggurat path per draw",
        "pcg64-mixed-32-64": "interleaved 32/64-bit draws + the `has_uint32`/`uinteger` buffer",
        "pcg64-choice": "`choice(arange(n))`",
        "pcg64-shuffle": "`shuffle` — NOT used by any injector (see the file's own note)",
        "cpython-mt-state": "the Mersenne Twister state after `init_by_array`",
        "cpython-random": (
            "`random`, `getrandbits`, `_randbelow`, `choice`, `shuffle`, `randint`, `randrange`"
        ),
        "quiz-layout": "the real option/pair orders (`quiz._shuffled`, salts 0/1/2/7)",
    }
    for name in sorted(files):
        rows = sum(1 for line in files[name].splitlines() if not line.startswith("#")) - 1
        lines.append(f"| `{name}.tsv` | {descriptions.get(name, '')} | {rows} |")
    lines += [
        "",
        f"Seeds: {len(VECTOR_SEEDS)} distinct — `{', '.join(str(s) for s in VECTOR_SEEDS)}`.",
        "The small ones are the seeds the figures and the probe sweeps actually use. The two large",
        "ones are real `print_seed` values (blake2b of an exercise key, modulo 2^62): the printed",
        "book draws there, and a SeedSequence that only handles small entropy would pass every other",
        "file and produce a different book.",
        "",
        f"Draw counts: {DRAWS_PER_SEED} per seed for the single-parameter primitives,",
        f"{DRAWS_PER_PARAM} per (seed, parameter) for the families that take bounds.",
        "",
        "## The three things a port gets wrong",
        "",
        "### 1. Seeding is not assignment",
        "",
        "`default_rng(7)` does not start PCG64 at 7. `seedsequence.tsv` carries both halves of what it",
        "does — the four expanded words, and the `(state, inc)` pair `pcg64_srandom_r` makes of them —",
        "so a port can tell which half is wrong instead of guessing. The arithmetic is written out in",
        "that file's header and implemented in `pcg64_state_from_words`.",
        "",
        "### 2. The 32-bit buffer hands out the LOW half first",
        "",
        "`next_uint32` draws one 64-bit word, returns its low half, and keeps the high half in",
        "`uinteger`. A 64-bit draw in between leaves the buffer alone. Get the halves the wrong way",
        "round and every 64-bit value in the port is right while every 32-bit one is wrong.",
        "`pcg64-mixed-32-64.tsv` records the buffer after every operation, so the first wrong row",
        "names the operation that broke it.",
        "",
        "### 3. `integers` and `choice` are 32-bit consumers",
        "",
        "This one is measured, and it is the finding a port is most likely to miss.",
        "`Generator.integers` routes through the **32-bit** generator whenever the requested range",
        "fits in 32 bits — regardless of the dtype asked for — and `choice` is `integers` underneath.",
        "So these two, which decide every exercise's label and every chart's price level, come out of",
        "the `has_uint32` buffer:",
        "",
        "| call | entry point | buffer |",
        "| --- | --- | --- |",
        "| `integers(0, n)` for `n - 1 <= 2**32 - 1` | `next_uint32` | consumed |",
        "| `integers(0, n)` above that | `next_uint64` | untouched |",
        "| `choice(a)` (one element, no `p`) | `next_uint32` | consumed |",
        "| `random()`, `uniform()`, `standard_normal()`, `random_raw()`, `shuffle()` |"
        " `next_uint64` | untouched |",
        "",
        "A port that reads `integers` from `next_uint64` produces perfect price noise and the wrong",
        "label, on every seed. `pcg64-mixed-32-64.tsv`'s `width` column is this table as data.",
        "",
        "### 4. `normal()` has three paths and only two of them call libm",
        "",
        "The ziggurat returns from a table lookup unless the draw falls outside its layer. `path` in",
        "`pcg64-normal.tsv` says which happened, measured rather than guessed: the instrument counts",
        "the 64-bit words the draw consumed (one = a table hit) and reads the value against",
        f"`r = {ZIGGURAT_NOR_R!r}` (above it = the tail produced it).",
        "",
        "**Seeds that enter the tail path** — the `log`-bearing branch, where a 1-ulp difference",
        "between two correct libms is allowed to appear in the raw double:",
        "",
        "| seed | fast | wedge (`exp`) | tail (`log`) |",
        "| --- | --- | --- | --- |",
    ]
    for seed, fast, wedge, tail in summary:
        mark = " **tail**" if tail else ""
        lines.append(f"| {seed}{mark} | {fast} | {wedge} | {tail} |")
    lines += [
        "",
        f"So over {DRAWS_PER_SEED} draws each, {len(tail_seeds)} of {len(VECTOR_SEEDS)} seeds reach the",
        f"tail: `{', '.join(str(s) for s in tail_seeds)}`. Every seed reaches the wedge, so `exp` is",
        "exercised everywhere and `log` only there.",
        "",
        "**These rows are informative, not binding.** Phase W1 measured the actual disagreement",
        "between glibc and `StrictMath` at 1 ulp on 4.86% of `exp` inputs and 0.79% of `log` inputs,",
        "and measured that perturbing *every* `exp`/`log` result by a full ulp moved **zero** of 845",
        "document fingerprints. The cross-language contract is therefore defined on the ROUNDED",
        "payload (`generation-goldens/`), and these doubles are here for debugging a port that is",
        "already failing — a raw-double comparison that fails on a tail row may be reporting a libm",
        "difference this project has decided to tolerate. Use `StrictMath`, never `Math`:",
        "`Math.exp` is a platform intrinsic and disagrees with `StrictMath.exp` on ~9.7% of Gaussian",
        "inputs with no stated bound. See the web repository's `phase-w1-numeric-sanitization.md`",
        "§3.",
        "",
        "## What is NOT here",
        "",
        "* **`SeedSequence.spawn`** beyond a token two-child example: no injector spawns. Every",
        "  generator in the generation path is `default_rng(<an int>)`.",
        "* **NumPy `shuffle`/`permutation`** as a live contract: no injector uses either. The file is",
        "  present and labelled so a future use starts pinned.",
        "* **`Random.gauss`/`normalvariate`**: the exercise machinery never draws a Gaussian from",
        "  CPython. All Gaussians are NumPy's.",
        "",
    ]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default {DEFAULT_OUT}")
    args = parser.parse_args(argv)

    started = time.monotonic()
    print(f"building PRNG vectors for {len(VECTOR_SEEDS)} seeds ...", flush=True)
    files = build_all()
    summary = tail_seed_summary()

    out: Path = args.out
    out.mkdir(parents=True, exist_ok=True)
    for stale in out.glob("*.tsv"):
        stale.unlink()
    for name, body in sorted(files.items()):
        (out / f"{name}.tsv").write_text(body, encoding="utf-8")
    (out / "README.md").write_text(readme_text(files, summary), encoding="utf-8")

    print()
    print("=" * 78)
    print(f"PRNG VECTORS  {out}")
    print("=" * 78)
    for name in sorted(files):
        rows = sum(1 for line in files[name].splitlines() if not line.startswith("#")) - 1
        print(f"  {name + '.tsv':<26} {rows:>8} rows")
    tail_seeds = [seed for seed, _f, _w, tail in summary if tail > 0]
    print(f"  {'README.md':<26} {'spec':>8}")
    print()
    print(f"ziggurat tail seeds  {len(tail_seeds)} of {len(VECTOR_SEEDS)}: {tail_seeds}")
    print(f"numpy {np.__version__} · python {sys.version.split()[0]} · {platform.machine()}")
    print(f"elapsed              {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
