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
    "candle_reaction:0": "f3592161214d7213",
    "candle_reaction:1": "32628a943af8bcfe",
    "candle_reaction:2": "1f5fca51b606ee96",
    "candle_reaction:3": "23ecb23c6423d573",
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
    "fakeout:0": "043db700deeda2ad",
    "fakeout:1": "57e6e71f34896c0f",
    "fakeout:2": "cb8e90271c796d31",
    "fakeout:3": "6dfb080d7cd322c1",
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
    "volume_confirmation:0": "0f21f7104405d9a2",
    "volume_confirmation:1": "9bed4212635f0e59",
    "volume_confirmation:2": "fbd1581abd0ca4b2",
    "volume_confirmation:3": "3a8c9341bb70585d",
    "wyckoff:0": "385d1ef85dd76d79",
    "wyckoff:1": "d3d68b466af5df0b",
    "wyckoff:2": "c919e3cc3977bef1",
    "wyckoff:3": "ad00ae665d810925",
    # Captured when the four FIGURE-ONLY injectors were ADDED (m08-l1 swing structure, m17-l2 + m06-l1
    # liquidity sweep, m21-l1 stop-limit gap, m24-l1 trade anatomy). They are registered like any other
    # injector — that is what puts them under the discovered level, credibility and annotation suites —
    # but no exercise config selects them: their whole subject is the resolution a figure shows and an
    # exercise may not. Kept as one group rather than filed alphabetically, so this addition reads as the
    # single event it was. Every hash above stayed byte-identical in the same commit, which is what proves
    # that the two things they added to shared code — `candle_extreme` and the `plan` level kind — touched
    # no existing generator path.
    "liquidity_sweep:0": "33e87d8a6d718f65",
    "liquidity_sweep:1": "24245e3ad81698c7",
    "liquidity_sweep:2": "fd2c2f805ae4ea57",
    "liquidity_sweep:3": "d4b3f8df0636cb1c",
    "market_structure:0": "95b2b2b265cdf541",
    "market_structure:1": "7f629f144edda030",
    "market_structure:2": "5c6ed95aeebb7922",
    "market_structure:3": "3f4dff5667efc0e5",
    "stop_limit_gap:0": "46b173dc594957eb",
    "stop_limit_gap:1": "8597f86ebbb5dd32",
    "stop_limit_gap:2": "ecc2a943ad23658d",
    "stop_limit_gap:3": "5df192595f0e130a",
    "trade_anatomy:0": "e8b93001f6b010de",
    "trade_anatomy:1": "29f82a1ec9e46d10",
    "trade_anatomy:2": "d8c8c4215544609c",
    "trade_anatomy:3": "92ea34b457f360e0",
    # Captured when the m30 SMC-dialect injectors were ADDED (`origin_zone`, `imbalance`) — the first two
    # to plant a shaded `Band`, and, unlike the group above, each feeding a figure AND an exercise. Kept as
    # one group for the same reason that one is: this was a single event. Every hash above stayed
    # byte-identical in the same commit, which is what proves the three additions to shared code touched
    # no existing generator path — the `bands` field on `PatternResult`/`FullPatternChart` (ground truth,
    # so it never enters the pre-answer payload these hashes cover), the conditional `bands` key on
    # `grade()`'s answer (like `oi`/`cvd` before it), and `grade()` reading `_full` instead of
    # `_instantiate`.
    #
    # That last one is the batch's ONLY edit to a shared code path, and these fingerprints cannot see it:
    # they cover `_instantiate`, which is not what changed. It has its own dedicated proof in
    # `test_chart_bands.py::test_grading_is_identical_whether_read_from_full_or_instantiate`, which
    # reconstructs the pre-change `grade()` for every registered injector and compares the two outputs.
    "imbalance:0": "9d7099f65136bff2",
    "imbalance:1": "bfa85922cc15a9db",
    "imbalance:2": "d92f571868493d78",
    "imbalance:3": "af5f347dd83d0d0d",
    "origin_zone:0": "75b31548d708875e",
    "origin_zone:1": "35837b9f3863204a",
    "origin_zone:2": "4fd664189c2442f1",
    "origin_zone:3": "c0a82bfb26bf6e5f",
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
