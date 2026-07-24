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
GOLDEN = {
    "derivatives:0": "4d0c4f23a1bce031",
    "derivatives:1": "51683f017c3352bb",
    "derivatives:2": "8a7b44998f5c4e9a",
    "derivatives:3": "4725287a1032e8fa",
    "divergence:0": "29992e7e823a2c73",
    "divergence:1": "20efe47486dbfeb6",
    "divergence:2": "80c2d1adcbc919db",
    "divergence:3": "1ea2efa1cd2f0773",
    "fakeout:0": "951ceea66d4ebf32",
    "fakeout:1": "3b6354709fc9565b",
    "fakeout:2": "5fb6cba619dfcf48",
    "fakeout:3": "343c7d0bb1442f81",
    "fibonacci:0": "3ab28c18effd08b8",
    "fibonacci:1": "8b504e4563b1e71d",
    "fibonacci:2": "24e876d34c071a91",
    "fibonacci:3": "b23a001bd35439d3",
    "ma_context:0": "cb916a4300a0f057",
    "ma_context:1": "575ba24b926a11f8",
    "ma_context:2": "f7668a9bf88ec8cc",
    "ma_context:3": "39f9cd9e8cc26deb",
    "oscillator_reading:0": "70342a8826e945b2",
    "oscillator_reading:1": "d3cf962a221bf0f6",
    "oscillator_reading:2": "433e75a44bca1d72",
    "oscillator_reading:3": "1f7ef799f6accb04",
    "volume_confirmation:0": "6b673e22ed3aa209",
    "volume_confirmation:1": "ae751257dd149708",
    "volume_confirmation:2": "4ff73de582518f0c",
    "volume_confirmation:3": "ccdde0c526fd9a52",
    "wyckoff:0": "b7d09e6c8be6227f",
    "wyckoff:1": "c67ab44de8ce0dd1",
    "wyckoff:2": "fca7cd7ae6412cb2",
    "wyckoff:3": "fe62d45700bf31c6",
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
