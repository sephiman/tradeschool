# SPDX-License-Identifier: AGPL-3.0-only
"""Wyckoff accumulation / distribution injector (module m09).

A DETECTION pattern. The learner reads the schematic — a prior trend, a trading range, and the
tell-tale false break inside it — and classifies it, WITHOUT seeing the resolution (the markup or
markdown that follows is off screen):

* ``accumulation`` — a prior DOWNTREND stalls into a range; a **spring** briefly breaks below range
  support and recovers back inside (smart money absorbing supply before a markup).
* ``distribution`` — a prior UPTREND stalls into a range; an **upthrust** briefly breaks above range
  resistance and fails back inside (supply overwhelming demand before a markdown).
* ``none``         — a plain range with no spring/upthrust and no clear prior trend.

Every label ends inside the range on a drift-free ambient tail, so the final candles cannot betray
the answer (the markup/markdown is never shown); the spring/upthrust sits mid-range, well left of the
tail. The range support/resistance are drawn as levels.
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
_EVENT_F = 0.74  # where the spring / upthrust sits (mid-range, left of the ambient tail)


class WyckoffInjector(PatternInjector):
    name: ClassVar[str] = "wyckoff"
    labels: ClassVar[tuple[str, ...]] = ("accumulation", "distribution", "none")
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "none"

    # Phase fractions (of the visible window) matching the shape built below. Used ONLY by lesson
    # figures to label phases A-E; never touches build()/exercise output (the golden test guards it).
    _PHASES: ClassVar[tuple[tuple[str, float], ...]] = (
        ("A", 0.14), ("B", 0.45), ("C", _EVENT_F), ("D", 0.86), ("E", 0.97),
    )

    def figure_annotations(self, target: str, n: int) -> list[Annotation]:
        """Figure-only phase labels A-E for the accumulation/distribution schematic (empty for 'none')."""
        if target == "none":
            return []
        kind = "low" if target == "accumulation" else "high"
        return [
            Annotation(index=WARMUP + int(frac * n), kind="marker" if letter != "C" else kind, label=letter)
            for letter, frac in self._PHASES
        ]

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        if target == "none":
            bound = float(rng.uniform(0.042, 0.05))
            pts = [
                (0.00, 0.00), (0.10, 0.028), (0.20, -0.03), (0.30, 0.03), (0.40, -0.028),
                (0.50, 0.03), (0.60, -0.03), (0.70, 0.028), (0.80, -0.025), (0.90, 0.025), (1.00, 0.0),
            ]
            shape = shape_from_points(pts, n)
            close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=0.008))
            apply_ambient_tail(rng, close_visible)
            return PatternResult(
                close_full=with_warmup(rng, close_visible),
                warmup=WARMUP,
                label=target,
                levels=[
                    Level(round(base * float(np.exp(bound)), 2), "resistance", "resistance"),
                    Level(round(base * float(np.exp(-bound)), 2), "support", "support"),
                ],
            )

        s = -1.0 if target == "accumulation" else 1.0  # range sits below base (acc) or above (dist)
        big_d = float(rng.uniform(0.11, 0.14))
        r = float(rng.uniform(0.05, 0.07))
        far, near, mid = s * big_d, s * (big_d - r), s * (big_d - r / 2)  # far = broken bound
        pts = [
            (0.00, -0.02 * s),          # prior trend starts on the opposite side of the range
            (0.12, 0.03 * s),           # trending into the range
            (0.22, near + s * 0.005),   # enter range (interior, just inside the near bound)
            (0.30, far - s * 0.010),    # to the far bound (interior)
            (0.40, near + s * 0.005), (0.50, far - s * 0.010), (0.60, near + s * 0.005),
            (0.68, far - s * 0.010),    # in range just before the event
            (_EVENT_F, far + s * 0.035),  # SPRING / UPTHRUST: break beyond the far bound
            (0.79, mid),                # recover back inside the range
            (0.86, near + s * 0.020), (1.00, near + s * 0.020),  # hold inside (no markup/markdown)
        ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=0.008))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)

        event_kind = "low" if target == "accumulation" else "high"
        event_idx = WARMUP + resolve_swing(close_visible, int(_EVENT_F * n), event_kind)
        far_price = round(base * float(np.exp(far)), 2)
        near_price = round(base * float(np.exp(near)), 2)
        if target == "accumulation":  # far bound is support (broken below), near is resistance
            levels = [Level(near_price, "resistance", "resistance"), Level(far_price, "support", "support")]
            event_label = "spring"
        else:  # far bound is resistance (broken above), near is support
            levels = [Level(far_price, "resistance", "resistance"), Level(near_price, "support", "support")]
            event_label = "upthrust"
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=event_idx, kind=event_kind, label=event_label)],
            levels=levels,
        )
