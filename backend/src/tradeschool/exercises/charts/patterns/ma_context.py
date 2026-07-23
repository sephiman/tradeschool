# SPDX-License-Identifier: AGPL-3.0-only
"""Moving-average context injector (module m10).

A CLASSIFICATION pattern: the label is the visible state, so there is no hidden resolution — the
learner reads the trend regime straight off the moving averages drawn on the price:

* ``uptrend``   — price above both MAs, the fast MA above the slow, both rising.
* ``downtrend`` — price below both MAs, the fast MA below the slow, both falling.
* ``range``     — the MAs are flat and intertwined; price chops across them.

Because the label IS on screen, the statistical "last candles must not predict the label" test does
not apply (the trend genuinely ends up/down); this injector ships the credibility half of the gate
instead — the ambient tail keeps the final candles free of any synthetic spike.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.indicators import ema
from tradeschool.exercises.charts.patterns.base import PatternInjector, PatternResult
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_FAST, _SLOW = 20, 50


class MaContextInjector(PatternInjector):
    name: ClassVar[str] = "ma_context"
    labels: ClassVar[tuple[str, ...]] = ("uptrend", "downtrend", "range")
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        def jig(scale: float) -> float:
            return float(rng.uniform(-scale, scale))

        if target in ("uptrend", "downtrend"):
            g = float(rng.uniform(0.18, 0.30))  # total log move across the window
            # A staircase: legs up with shallower pullbacks, so MAs trail below a rising price.
            pts = [
                (0.00, 0.00), (0.16, 0.28 * g + jig(0.01)), (0.28, 0.18 * g + jig(0.01)),
                (0.44, 0.52 * g + jig(0.01)), (0.58, 0.44 * g + jig(0.01)),
                (0.74, 0.78 * g + jig(0.01)), (0.86, 0.72 * g + jig(0.01)), (1.00, g),
            ]
            sign = 1.0 if target == "uptrend" else -1.0
            pts = [(f, sign * y) for f, y in pts]
            amp = 0.02
        else:  # range: flat net drift, MAs intertwine
            pts = [
                (0.00, 0.00), (0.14, 0.05 + jig(0.01)), (0.30, -0.045 + jig(0.01)),
                (0.46, 0.04 + jig(0.01)), (0.62, -0.05 + jig(0.01)), (0.78, 0.045 + jig(0.01)),
                (0.90, -0.02 + jig(0.01)), (1.00, 0.00),
            ]
            amp = 0.022

        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=amp))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)

        fast = ema(close_full, _FAST)
        slow = ema(close_full, _SLOW)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            overlays={f"ema{_FAST}": fast.tolist(), f"ema{_SLOW}": slow.tolist()},
        )
