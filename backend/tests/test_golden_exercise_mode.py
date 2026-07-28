# SPDX-License-Identifier: AGPL-3.0-only
"""Golden-master lock on EXERCISE-MODE chart output.

Phase-3 adds a figure-only "resolution continuation" branch. The hard rule: it must never change what
an exercise renders. This test fingerprints the full exercise-mode output (all OHLCV + rsi + macd + oi
+ overlays + levels + ground-truth label + annotations) for a fixed set of seeds per injector and for
the frozen divergence generator, and asserts it byte-for-byte matches the baseline captured before any
figure work. If a figure change touches an exercise path, a fingerprint flips and this fails — that is
the signal to stop and flag the injector rather than adapt its exercise path silently.
"""

from __future__ import annotations

import hashlib
import json

from tradeschool.exercises.charts.patterns.registry import all_injectors
from tradeschool.exercises.pattern_chart import PatternChartGenerator
from tradeschool.exercises.pattern_chart import _instantiate as pattern_instantiate
from tradeschool.exercises.synthetic_chart import SyntheticChartGenerator
from tradeschool.exercises.synthetic_chart import _instantiate as divergence_instantiate

# Baseline captured from the exercise generators BEFORE the figure/resolution work. Do not edit these
# to make the test pass — a mismatch means exercise output changed, which is the bug this guards.
#
# RE-CAPTURED ONCE, deliberately, for the drawn-level integrity fix (see tests/test_chart_levels.py).
# Every injector that draws a horizontal level was placing it where the price action never went: the
# range's swings stopped 2.4-3.6% short of the line (`fakeout`, `volume_confirmation`), the bounds sat
# outside the range they were supposed to contain (`wyckoff`), and `candle_reaction` published the
# reaction candle's own wick extreme instead of the level its approach was built against. In 100% of
# sampled seeds the drawn level had ZERO touches before the decision, and `no_break` printed a wick
# through its own level in 56% — the one thing its label denies. Fixing that necessarily moved the
# candles, so these 16 fingerprints moved with it:
#
#   candle_reaction:0-3        level now derived from `_GAP`; rejection wick anchored to the line
#   fakeout:0-3                range rewritten as distances inside `gap` so it tests the level twice
#   volume_confirmation:0-3    same range rewrite (it shares fakeout's geometry)
#   wyckoff:0-3                bound margins widened past the noise peak; tail held inside the range
#
# Nothing else moved, and that is the point: `divergence`, `fibonacci`, `ma_context`, `macd_cross`,
# `oscillator_reading`, `derivatives` and `cvd_divergence` are byte-identical below, which is what
# proves the fix touched exactly the injectors whose levels were wrong and no others.
GOLDEN = {
    "candle_reaction:0": "8b4095b146838fd0",
    "candle_reaction:1": "dace485d6a39c028",
    "candle_reaction:2": "9737236dd314f3ea",
    "candle_reaction:3": "841065ace006b2b0",
    # Captured when the m26 CVD-divergence injector was ADDED. Its `cvd_full` pane series reaches the
    # payload through the same CONDITIONAL key the `oi` pane uses, so every hash above stayed
    # byte-identical in the same commit — which is what proves the new pane series is purely additive.
    "cvd_divergence:0": "e1ee9199b6ab71a0",
    "cvd_divergence:1": "ff862cacbac02fa9",
    "cvd_divergence:2": "5b7614ea100b3f25",
    "cvd_divergence:3": "5adcc75d04bce641",
    "derivatives:0": "4d0c4f23a1bce031",
    "derivatives:1": "51683f017c3352bb",
    "derivatives:2": "8a7b44998f5c4e9a",
    "derivatives:3": "4725287a1032e8fa",
    "divergence:0": "29992e7e823a2c73",
    "divergence:1": "20efe47486dbfeb6",
    "divergence:2": "80c2d1adcbc919db",
    "divergence:3": "1ea2efa1cd2f0773",
    "fakeout:0": "fff0fb97486f2348",
    "fakeout:1": "13a38e198c7fe35e",
    "fakeout:2": "7afbecd5578ff18b",
    "fakeout:3": "9e95cd13d6f77569",
    "fibonacci:0": "3ab28c18effd08b8",
    "fibonacci:1": "8b504e4563b1e71d",
    "fibonacci:2": "24e876d34c071a91",
    "fibonacci:3": "b23a001bd35439d3",
    "ma_context:0": "cb916a4300a0f057",
    "ma_context:1": "575ba24b926a11f8",
    "ma_context:2": "f7668a9bf88ec8cc",
    "ma_context:3": "39f9cd9e8cc26deb",
    # Captured when the m11 MACD-crossover injector was ADDED (a new key is the one legitimate reason
    # this dict grows; the same commit left every hash above untouched, which is what proves the
    # `with_warmup(drift=…, sigma=…)` it needed stayed byte-identical for the existing injectors).
    "macd_cross:0": "db720b2714f34720",
    "macd_cross:1": "dc7eccc53e9e3cb3",
    "macd_cross:2": "ad2f17dfd385c052",
    "macd_cross:3": "86e85bc722b63d0d",
    "oscillator_reading:0": "70342a8826e945b2",
    "oscillator_reading:1": "d3cf962a221bf0f6",
    "oscillator_reading:2": "433e75a44bca1d72",
    "oscillator_reading:3": "1f7ef799f6accb04",
    "volume_confirmation:0": "10dd51f6e2cf4e6b",
    "volume_confirmation:1": "40c4d327a27bdffd",
    "volume_confirmation:2": "2e9573ecb0f93c2b",
    "volume_confirmation:3": "069d7f71b014fbee",
    "wyckoff:0": "385d1ef85dd76d79",
    "wyckoff:1": "d3d68b466af5df0b",
    "wyckoff:2": "c919e3cc3977bef1",
    "wyckoff:3": "ad00ae665d810925",
}

_SEEDS = range(4)


def _fp(obj: object) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:16]


def _current() -> dict[str, str]:
    pg = PatternChartGenerator()
    out: dict[str, str] = {}
    for inj in all_injectors():
        labels = list(inj.labels)
        cfg = pg.parse_config(
            {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": inj.name,
             "n": 130, "targets": labels, "choices": labels}
        )
        for seed in _SEEDS:
            label, ann, payload = pattern_instantiate(cfg, seed)
            out[f"{inj.name}:{seed}"] = _fp({"p": payload, "label": label, "ann": ann})

    sg = SyntheticChartGenerator()
    scfg = sg.parse_config(
        {"type": "synthetic_chart", "prompt": {"en": "x", "es": "x"}, "indicator": "rsi", "n": 120,
         "targets": ["none", "bullish_regular", "bearish_regular"],
         "choices": ["none", "bullish_regular", "bearish_regular"]}
    )
    for seed in _SEEDS:
        tgt, s1, s2, payload = divergence_instantiate(scfg, seed)
        out[f"divergence:{seed}"] = _fp({"p": payload, "t": tgt.value, "s1": s1, "s2": s2})
    return out


def test_exercise_mode_output_is_byte_identical_to_baseline() -> None:
    current = _current()
    # Coverage: every registered injector (across seeds) plus divergence is fingerprinted.
    assert set(current) == set(GOLDEN), "fingerprint set changed — an injector was added/removed?"
    mismatches = {k: (GOLDEN[k], current[k]) for k in GOLDEN if current[k] != GOLDEN[k]}
    assert not mismatches, f"exercise-mode output changed (figure work must not touch it): {mismatches}"
