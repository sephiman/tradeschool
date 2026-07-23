# SPDX-License-Identifier: AGPL-3.0-only
"""Oscillator-reading injector (module m11).

A CLASSIFICATION pattern: read the CURRENT state of the RSI shown beneath the price.

* ``overbought`` — a sustained recent rally pushes RSI above 70.
* ``oversold``   — a sustained recent decline pushes RSI below 30.
* ``neutral``    — choppy, balanced price keeps RSI mid-range (~40-60).

The label is the visible reading, so there is no hidden resolution and the "last candles must not
predict the label" test does not apply — the recent move IS the signal. No ambient tail is applied
(that would flatten the very move being read); instead the ends are gentle bounded noise, so the
credibility test (no synthetic spike) still holds. m11's lesson makes the point that an overbought
reading in a strong trend is not itself a sell — but classifying the reading is the drill here.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.patterns.base import PatternInjector, PatternResult
from tradeschool.exercises.charts.patterns.common import WARMUP, bounded_noise, shape_from_points, with_warmup

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)


class OscillatorReadingInjector(PatternInjector):
    name: ClassVar[str] = "oscillator_reading"
    labels: ClassVar[tuple[str, ...]] = ("overbought", "oversold", "neutral")
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "rsi"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        def jig(s: float) -> float:
            return float(rng.uniform(-s, s))

        if target in ("overbought", "oversold"):
            # An early wander, then a STAIRCASE rally into the right edge — up-legs with small
            # pullbacks. The recent window is gain-dominated so RSI stretches past 70, but the
            # counter-moves keep it off the 100 peg (round-3 credibility). Negate for oversold.
            g = float(rng.uniform(0.20, 0.30))
            pts = [
                (0.00, 0.00), (0.16, jig(0.02)), (0.32, 0.03 + jig(0.01)), (0.46, 0.01 + jig(0.01)),
                (0.56, 0.20 * g), (0.64, 0.10 * g), (0.72, 0.40 * g), (0.80, 0.30 * g),
                (0.88, 0.62 * g), (0.94, 0.52 * g), (0.98, 0.85 * g), (1.00, g),
            ]
            sign = 1.0 if target == "overbought" else -1.0
            shape = shape_from_points([(f, sign * y) for f, y in pts], n)
            # A correlated (walk) texture is fine: the strong shape sets the direction.
            noise = bounded_noise(rng, n, amp=0.012)
        else:  # neutral — a clean symmetric zig-zag with IID (directionless) noise. RSI is
            # scale-invariant, so what matters is that up and down moves stay balanced in every
            # window; a correlated walk would create local runs that lean the reading, so use IID.
            pts = [
                (0.00, 0.00), (0.10, 0.012), (0.20, -0.012), (0.30, 0.012), (0.40, -0.012),
                (0.50, 0.012), (0.60, -0.012), (0.70, 0.012), (0.80, -0.012), (0.90, 0.012),
                (1.00, -0.004),
            ]
            shape = shape_from_points(pts, n)
            noise = rng.normal(0.0, 0.004, n)

        close_visible = base * np.exp(shape + noise)
        close_full = with_warmup(rng, close_visible)
        return PatternResult(close_full=close_full, warmup=WARMUP, label=target)
