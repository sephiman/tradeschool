# SPDX-License-Identifier: AGPL-3.0-only
"""Wyckoff accumulation / distribution injector (m09).

A DETECTION pattern: a prior trend, a range, and the tell-tale false break inside it, classified
without seeing the markup/markdown that follows. Every label ends inside the range on an ambient tail,
with the spring/upthrust well left of it, so the final candles cannot betray the answer.
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
    clamp_close_inside,
    resolve_swing,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_EVENT_F = 0.74  # where the spring / upthrust sits (mid-range, left of the ambient tail)
# How far inside a range bound the swings that define it turn, and the bounded peak of the candle
# texture. The margin must exceed the noise peak so texture alone never carries a close through a bound.
_TEST = 0.014
_NOISE = 0.005
_HOLD_IN = 0.030  # where the post-event hold sits inside the unbroken bound (out of the tail's reach)
_RANGE_F = 0.24  # by here the prior trend has entered the range, so both bounds start applying
_EVENT_RAMP_F = 0.66  # the spring/upthrust ramp is already through the far bound by the time it peaks
_RECOVER_F = 0.79  # by here price has recovered back inside, so the far bound applies again


def _swing_of(kind: str) -> str:
    """The swing that TESTS a bound: a resistance is tested by a high, a support by a low."""
    return "high" if kind == "resistance" else "low"


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
            # The swings are written as distances INSIDE `bound`, so the range actually oscillates
            # BETWEEN the two drawn lines. They used to be a flat ±0.028 against bounds 4.2-5% out, so
            # a plain range rendered with two boundary lines it never came near (0.1 touching bars per
            # chart) — the drawn box did not contain the price.
            edge = bound - _TEST
            pts = [
                (0.00, 0.00), (0.10, edge), (0.20, -edge), (0.30, edge), (0.40, -edge),
                (0.50, edge), (0.60, -edge), (0.70, edge), (0.80, -edge), (0.90, edge), (1.00, 0.0),
            ]
            shape = shape_from_points(pts, n)
            close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
            apply_ambient_tail(rng, close_visible)
            hi_price = round(base * float(np.exp(bound)), 2)
            lo_price = round(base * float(np.exp(-bound)), 2)
            # Neither bound is ever broken in a plain range — that is the whole label — so the tail's
            # random walk is held inside both.
            clamp_close_inside(close_visible, hi_price, "resistance")
            clamp_close_inside(close_visible, lo_price, "support")
            close_full = with_warmup(rng, close_visible)
            # A range with no spring/upthrust is exactly the label "neither bound was broken", so both
            # lines are held for the whole window and the swings that define them must reach them.
            hi_tests = tuple(
                WARMUP + resolve_swing(close_visible, int(f * n), "high") for f in (0.30, 0.50, 0.70)
            )
            lo_tests = tuple(
                WARMUP + resolve_swing(close_visible, int(f * n), "low") for f in (0.20, 0.40, 0.60)
            )
            whole = ((0, len(close_full)),)
            return PatternResult(
                close_full=close_full,
                warmup=WARMUP,
                label=target,
                levels=[
                    Level(hi_price, "resistance", "resistance"),
                    Level(lo_price, "support", "support"),
                ],
                level_guards=[
                    LevelGuard(hi_price, "resistance", tests=hi_tests, no_breach=whole),
                    LevelGuard(lo_price, "support", tests=lo_tests, no_breach=whole),
                ],
            )

        s = -1.0 if target == "accumulation" else 1.0  # range sits below base (acc) or above (dist)
        big_d = float(rng.uniform(0.11, 0.14))
        r = float(rng.uniform(0.05, 0.07))
        far, near, mid = s * big_d, s * (big_d - r), s * (big_d - r / 2)  # far = broken bound
        # Both bounds are approached to within `_TEST` — a range's boundaries are only boundaries if the
        # swings inside it reach them. The interior margins used to be 0.005/0.010 against a noise peak
        # of 0.008, so the texture alone could carry a close through the UNBROKEN bound: a range that
        # quietly breaks the side the label says held.
        pts = [
            (0.00, -0.02 * s),          # prior trend starts on the opposite side of the range
            (0.12, 0.03 * s),           # trending into the range
            (0.22, near + s * _TEST),   # enter range (interior, just inside the near bound)
            (0.30, far - s * _TEST),    # to the far bound (interior)
            (0.40, near + s * _TEST), (0.50, far - s * _TEST), (0.60, near + s * _TEST),
            (0.68, far - s * _TEST),    # in range just before the event
            (_EVENT_F, far + s * 0.035),  # SPRING / UPTHRUST: break beyond the far bound
            (0.79, mid),                # recover back inside the range
            # Hold mid-range, far enough inside the near bound that the ambient tail cannot drift
            # through it and print a break the label never claimed.
            (0.86, near + s * _HOLD_IN), (1.00, near + s * _HOLD_IN),
        ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)

        event_kind = "low" if target == "accumulation" else "high"
        far_price = round(base * float(np.exp(far)), 2)
        near_price = round(base * float(np.exp(near)), 2)
        far_kind = "support" if target == "accumulation" else "resistance"
        near_kind = "resistance" if target == "accumulation" else "support"
        # The near bound holds from the range entry on, the far bound again once the spring/upthrust has
        # recovered back inside — so the tail cannot drift through either and undo the schematic.
        clamp_close_inside(close_visible, near_price, near_kind, start=int(_RANGE_F * n))
        clamp_close_inside(close_visible, far_price, far_kind, start=int(_RECOVER_F * n))
        close_full = with_warmup(rng, close_visible)
        event_idx = WARMUP + resolve_swing(close_visible, int(_EVENT_F * n), event_kind)
        if target == "accumulation":  # far bound is support (broken below), near is resistance
            levels = [Level(near_price, "resistance", "resistance"), Level(far_price, "support", "support")]
            event_label = "spring"
        else:  # far bound is resistance (broken above), near is support
            levels = [Level(far_price, "resistance", "resistance"), Level(near_price, "support", "support")]
            event_label = "upthrust"
        near_tests = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), _swing_of(near_kind))
            for f in (0.22, 0.40, 0.60)
        )
        far_tests = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), _swing_of(far_kind))
            for f in (0.30, 0.50, 0.68)
        )
        # Once price is INSIDE the range the near bound holds — that it was never breached is half the
        # schematic. It is only guarded from the range entry on: the prior trend legitimately starts on
        # the far side of it (that is what "a trend stalls into a range" means), so guarding from bar 0
        # would clamp the approach's wicks flat against their own bodies.
        # The far bound holds everywhere EXCEPT the spring/upthrust, which is the other half.
        range_in = WARMUP + int(_RANGE_F * n)
        # The exemption opens at the last in-range control point (0.68), not at the event fraction: the
        # ramp into the spring is already through the bound a bar or two before it peaks.
        event_lo, event_hi = WARMUP + int(_EVENT_RAMP_F * n), WARMUP + int(_RECOVER_F * n)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=event_idx, kind=event_kind, label=event_label)],
            levels=levels,
            level_guards=[
                LevelGuard(
                    near_price, near_kind, tests=near_tests, no_breach=((range_in, len(close_full)),)
                ),
                LevelGuard(
                    far_price,
                    far_kind,
                    tests=far_tests,
                    no_breach=((range_in, event_lo), (event_hi, len(close_full))),
                ),
            ],
        )
