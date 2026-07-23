# SPDX-License-Identifier: AGPL-3.0-only
"""Breakout / fakeout injector (module m08).

A horizontal level (support or resistance) is tested near the right edge. The learner classifies the
OUTCOME that is on screen — not a hidden future move:

* ``genuine_breakout`` — price closed decisively beyond the level and is holding there.
* ``false_break``      — price broke beyond the level, then closed back inside and is holding inside.
* ``no_break``         — price approached the level, was rejected and never traded beyond it.

The "resolution" (the trend that a real breakout unleashes) is off screen: after the decision the
series is flat and then a drift-free ambient tail, identical for every label, so the final candles
can't leak the answer (Phase-1 round-6 rule). The tell is structural and visible: where price sits
relative to the drawn level line, and whether it ever closed beyond it.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    Level,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    resolve_swing,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# Decision fraction (where the level is tested) and the flat hold that follows, before the ambient
# tail. Kept well left of the right edge so the last candles are pure ambient noise.
_DECIDE = 0.80
_HOLD = 0.88


class FakeoutInjector(PatternInjector):
    name: ClassVar[str] = "fakeout"
    labels: ClassVar[tuple[str, ...]] = ("genuine_breakout", "false_break", "no_break")
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "rsi"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        # The level is above the range (resistance) or below it (support); `sign` mirrors the whole
        # construction so both read identically ("did the tested level break and hold?").
        resistance = bool(rng.integers(0, 2))
        sign = 1.0 if resistance else -1.0
        gap = float(rng.uniform(0.052, 0.064))  # log-distance from the range midline to the level

        # Range wiggle safely below the level for the first ~3/4 of the window. Amplitude and noise
        # are kept a wide margin (>6 sigma) inside `gap`, so noise alone never fakes a break.
        def j(lo: float, hi: float) -> float:
            return float(rng.uniform(lo, hi))

        pts: list[tuple[float, float]] = [
            (0.00, 0.0), (0.10, j(0.008, 0.024)), (0.20, j(-0.026, -0.008)),
            (0.32, j(0.010, 0.026)), (0.45, j(-0.028, -0.010)), (0.58, j(0.008, 0.024)),
            (0.70, j(-0.018, 0.002)), (0.76, 0.028),
        ]
        # The decision at ~0.80, then a flat hold at the post-decision level (relative to `gap`).
        if target == "genuine_breakout":  # closes decisively beyond and holds beyond
            pts += [(_DECIDE, gap + 0.028), (_HOLD, gap + 0.030), (1.00, gap + 0.030)]
        elif target == "false_break":  # pokes beyond, then closes back inside and holds inside
            pts += [(_DECIDE, gap + 0.015), (0.84, gap + 0.015), (_HOLD, gap - 0.030), (1.00, gap - 0.030)]
        elif target == "no_break":  # tests the level (rises to just under it) and is rejected below
            pts += [(_DECIDE, gap - 0.013), (_HOLD, gap - 0.020), (1.00, gap - 0.020)]
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown fakeout label {target!r}")

        shape = shape_from_points([(f, sign * y) for f, y in pts], n)
        # Peak texture (0.010) stays a margin inside the smallest separation (0.013), so noise alone
        # never crosses the level — the label is carried entirely by the designed shape.
        noise = bounded_noise(rng, n, amp=0.010)
        close_visible = base * np.exp(shape + noise)
        apply_ambient_tail(rng, close_visible)

        close_full = with_warmup(rng, close_visible)
        level_price = base * float(np.exp(sign * gap))
        decide_idx = WARMUP + resolve_swing(
            close_visible, int(_DECIDE * n), "high" if resistance else "low"
        )
        kind = "resistance" if resistance else "support"
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=decide_idx, kind="marker", label="test")],
            levels=[Level(price=round(level_price, 2), label=kind, kind=kind)],
        )
