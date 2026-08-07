# SPDX-License-Identifier: AGPL-3.0-only
"""Fibonacci-retracement injector (m13): which grid level the pullback reached.

Fibonacci arithmetic is done in PRICE space — retracements are linear in price, not log. A
CLASSIFICATION pattern, so no last-candle leak test.
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
_RATIOS = {"retrace_382": 0.382, "retrace_500": 0.5, "retrace_618": 0.618}
_SWING_F, _PULLBACK_F = 0.50, 0.80  # fractions of the window for the swing end and the pullback low


class FibonacciInjector(PatternInjector):
    name: ClassVar[str] = "fibonacci"
    labels: ClassVar[tuple[str, ...]] = ("retrace_382", "retrace_500", "retrace_618")
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        up = bool(rng.integers(0, 2))  # up impulse + down pullback, or the mirror
        s = 1.0 if up else -1.0
        big_l = float(rng.uniform(0.20, 0.30))
        ratio = _RATIOS[target]

        swing_end = base * float(np.exp(s * big_l))
        impulse = swing_end - base
        pullback_price = base + (1.0 - ratio) * impulse  # price at the labelled retracement
        e_off = float(np.log(swing_end / base))
        p_off = float(np.log(pullback_price / base))
        span = e_off - p_off  # signed distance from swing end to the pullback extreme

        pts = [
            (0.00, 0.00), (0.12, 0.25 * e_off), (0.28, 0.56 * e_off), (0.42, 0.90 * e_off),
            (_SWING_F, e_off),                     # swing end (impulse complete)
            (0.60, e_off - 0.40 * span),           # pulling back
            # A short plateau AT the pullback extreme so the 3-window smoothing does not lift it away
            # from the labelled fib level.
            (0.76, p_off), (_PULLBACK_F, p_off), (0.84, p_off),
            (0.90, p_off + 0.15 * span), (1.00, p_off + 0.12 * span),
        ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=0.008))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)

        levels = [
            Level(price=round(base + (1.0 - f) * impulse, 2), label=name.split("_")[1], kind="fib")
            for name, f in _RATIOS.items()
        ]
        swing_kind_end = "high" if up else "low"
        swing_kind_pull = "low" if up else "high"
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[
                Annotation(WARMUP + resolve_swing(close_visible, int(_SWING_F * n), swing_kind_end),
                           swing_kind_end, "swing"),
                Annotation(WARMUP + resolve_swing(close_visible, int(_PULLBACK_F * n), swing_kind_pull),
                           swing_kind_pull, "pullback"),
            ],
            levels=levels,
        )
