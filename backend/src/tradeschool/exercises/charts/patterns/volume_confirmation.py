# SPDX-License-Identifier: AGPL-3.0-only
"""Volume-confirmation injector (module m14).

A DETECTION pattern where the tell is VOLUME, not price. Price breaks a level and holds just beyond
it — identically for both labels — so price alone cannot betray the answer:

* ``confirmed_breakout``   — the breakout candle prints on a clear volume surge (participation).
* ``unconfirmed_breakout`` — the same break happens on weak, below-average volume (no participation).

Because the price geometry is the same for both labels, the last-candle price distribution is
identical (the anti-leak test passes trivially) and the resolution — whether the break ultimately
holds or fails — is off screen. The learner must read the volume bars under the breakout. Volume is
supplied explicitly (overriding the engine's price-derived volume) so it carries the signal.
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
_BASE_VOLUME = 1000.0
_DECIDE, _HOLD = 0.80, 0.88
_BREAK_LO, _BREAK_HI = 0.77, 0.87  # window (window-fractions) that carries the breakout volume


class VolumeConfirmationInjector(PatternInjector):
    name: ClassVar[str] = "volume_confirmation"
    labels: ClassVar[tuple[str, ...]] = ("confirmed_breakout", "unconfirmed_breakout")
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        resistance = bool(rng.integers(0, 2))
        sign = 1.0 if resistance else -1.0
        gap = float(rng.uniform(0.050, 0.064))

        def j(lo: float, hi: float) -> float:
            return float(rng.uniform(lo, hi))

        # Range, then a break beyond the level that holds — IDENTICAL shape for both labels.
        pts = [
            (0.00, 0.0), (0.10, j(0.008, 0.024)), (0.20, j(-0.026, -0.008)), (0.32, j(0.010, 0.026)),
            (0.45, j(-0.028, -0.010)), (0.58, j(0.008, 0.024)), (0.70, j(-0.018, 0.002)),
            (0.76, 0.028), (_DECIDE, gap + 0.026), (_HOLD, gap + 0.030), (1.00, gap + 0.030),
        ]
        shape = shape_from_points([(f, sign * y) for f, y in pts], n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=0.010))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)

        # Volume: a noisy baseline, with the breakout window either surging or staying weak.
        total = WARMUP + n
        volume = _BASE_VOLUME * (0.75 + 0.5 * np.abs(rng.normal(0.0, 1.0, total)))
        b0, b1 = WARMUP + int(_BREAK_LO * n), WARMUP + int(_BREAK_HI * n)
        if target == "confirmed_breakout":
            volume[b0:b1] *= rng.uniform(3.0, 4.2)  # a clear participation surge
        elif target == "unconfirmed_breakout":
            volume[b0:b1] *= rng.uniform(0.5, 0.8)  # the break happens on thin volume
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown volume label {target!r}")

        decide_idx = WARMUP + resolve_swing(close_visible, int(_DECIDE * n), "high" if resistance else "low")
        kind = "resistance" if resistance else "support"
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=decide_idx, kind="marker", label="break")],
            levels=[Level(price=round(base * float(np.exp(sign * gap)), 2), label=kind, kind=kind)],
            volume_full=volume,
        )
