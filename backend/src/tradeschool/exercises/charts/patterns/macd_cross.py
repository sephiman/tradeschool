# SPDX-License-Identifier: AGPL-3.0-only
"""MACD-crossover injector (m11).

A CLASSIFICATION pattern, separated by one on-screen quantity: how often the MACD line crosses ZERO —
never, once and late, or repeatedly. Every label is built in both directions, so the chart's direction
never hints at the answer.

No ambient tail (like ``oscillator_reading``): overwriting the final candles would flatten the very
cross being read. Gentle bounded noise instead, so the no-synthetic-spike gate still holds.

Needs a *trending* warm-up (``with_warmup(drift=…)``), unlike every other injector — a flat one leaves
the MACD wandering across zero at the left edge, printing a crossing the label does not claim.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.patterns.base import PatternInjector, PatternResult
from tradeschool.exercises.charts.patterns.common import WARMUP, bounded_noise, shape_from_points, with_warmup

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
# Log-price the warm-up climbs (or falls) into the visible window, at a slope close to the visible
# trend's, so the MACD line enters the left edge already on the side the label needs.
_WARM_DRIFT = 0.08
_WARM_SIGMA = 0.003  # quieter than the default warm-up: its noise must not swamp that drift


class MacdCrossInjector(PatternInjector):
    name: ClassVar[str] = "macd_cross"
    labels: ClassVar[tuple[str, ...]] = ("signal_cross", "zero_cross", "whipsaw")
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "macd"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        def jig(s: float) -> float:
            return float(rng.uniform(-s, s))

        sign = 1.0 if rng.random() < 0.5 else -1.0  # +1 bullish reading, -1 its mirror

        if target == "signal_cross":
            # A staircase trend strong enough to hold the MACD line clear of zero throughout, with
            # ONE shallow pullback near the right edge: the pullback rolls the MACD line down under
            # its signal (histogram negative), and the resumption — steepening into the last candles
            # so the read does not fade — takes it back above (histogram positive). Fast and slow EMA
            # never swap order, so the zero line is never touched.
            g = float(rng.uniform(0.26, 0.36))  # total log move across the window
            pts = [
                (0.00, 0.00), (0.20, 0.22 * g + jig(0.008)), (0.30, 0.20 * g + jig(0.008)),
                (0.46, 0.40 * g + jig(0.008)), (0.54, 0.38 * g),
                (0.68, 0.68 * g), (0.76, 0.62 * g),
                (0.88, 0.78 * g), (1.00, g),
            ]
            amp, drift = 0.012, sign * _WARM_DRIFT
        elif target == "zero_cross":
            # A sustained move one way (counter-legs kept shallow and short, so the MACD line never
            # pokes back over zero early), then a decisive turn from ~0.70 that drags the fast EMA
            # through the slow one: exactly one zero crossing, in the last third, with the rest of
            # the window on the other side of it.
            d = float(rng.uniform(0.22, 0.32))
            pts = [
                (0.00, 0.00), (0.16, -0.32 * d), (0.24, -0.29 * d),
                (0.46, -0.58 * d), (0.53, -0.55 * d), (0.70, -0.66 * d),
                (0.80, -0.50 * d), (0.90, -0.24 * d), (0.96, -0.06 * d), (1.00, 0.04 * d),
            ]
            amp, drift = 0.012, -sign * _WARM_DRIFT  # the warm-up continues the PRIOR trend
        else:  # whipsaw — a flat range whose swings are short enough relative to the 12/26 EMAs that
            # the MACD line never settles: it crosses zero six-plus times and the window closes on yet
            # another fresh cross that will lead nowhere either. Turns are WALKED FORWARD with a random
            # leg length and reach rather than laid out on a fixed grid — evenly spaced, equal-height
            # swings render as a sine wave, which no real market prints. Legs stay long enough (~9-20
            # candles, so a full swing is ~20-40) that the two EMAs still change order on each one,
            # which is what keeps the zero line getting crossed.
            a = float(rng.uniform(0.038, 0.052))
            pts = [(0.00, 0.00)]
            at, side = 0.0, 1.0
            while at < 0.94:
                at = min(1.0, at + float(rng.uniform(0.085, 0.155)))
                pts.append((at, side * a * float(rng.uniform(0.70, 1.15))))
                side = -side
            if pts[-1][0] < 1.0:  # close the window mid-swing, on a partial leg the other way
                pts.append((1.00, side * a * 0.25))
            amp, drift = 0.018, 0.0  # no drift: the warm-up must not lend the range a trend

        shape = shape_from_points([(f, sign * y) for f, y in pts], n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=amp))
        close_full = with_warmup(rng, close_visible, drift=drift, sigma=_WARM_SIGMA)
        return PatternResult(close_full=close_full, warmup=WARMUP, label=target)
