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
    LevelGuard,
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
_BREAK_F = 0.78  # where the decision ramp crosses the level; the range before it must hold the line
_TEST = 0.014  # how far inside the level the range's two designed tests sit
_NOISE = 0.005  # bounded peak of the candle texture — well inside `_TEST`, so it never fakes a break
_HOLD_D = 0.045  # post-break hold distance beyond the level (out of the ambient tail's reach)


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

        # Range, then a break beyond the level that holds — IDENTICAL shape for both labels. As in the
        # fakeout injector this range is written as distances INSIDE `gap`, so it TESTS the drawn level
        # twice instead of wandering a fixed 0.028 below a line 5-6.4% away that no candle ever reached.
        def inside(d: float) -> float:
            return gap - d

        pts = [
            (0.00, inside(j(0.050, 0.062))),
            (0.10, inside(j(0.018, 0.028))),
            (0.20, inside(j(0.052, 0.064))),
            (0.32, inside(_TEST)),  # first test of the level
            (0.45, inside(j(0.054, 0.066))),
            (0.58, inside(_TEST)),  # second test — two touches are what define the line
            (0.70, inside(j(0.040, 0.052))),
            (0.76, inside(0.026)),
            (_DECIDE, gap + 0.026), (_HOLD, gap + _HOLD_D), (1.00, gap + _HOLD_D),
        ]
        shape = shape_from_points([(f, sign * y) for f, y in pts], n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
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

        swing_kind = "high" if resistance else "low"
        decide_idx = WARMUP + resolve_swing(close_visible, int(_DECIDE * n), swing_kind)
        test_idx = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), swing_kind) for f in (0.32, 0.58)
        )
        kind = "resistance" if resistance else "support"
        level_price = round(base * float(np.exp(sign * gap)), 2)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=decide_idx, kind="marker", label="break")],
            levels=[Level(price=level_price, label=kind, kind=kind)],
            level_guards=[
                LevelGuard(
                    price=level_price,
                    kind=kind,
                    tests=(*test_idx, decide_idx),
                    # The break itself is the point, so only the range before it is held to the line.
                    no_breach=((0, WARMUP + int(_BREAK_F * n)),),
                )
            ],
            volume_full=volume,
        )
