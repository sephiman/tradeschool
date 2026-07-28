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

# Decision fraction (where the level is tested) and the flat hold that follows, before the ambient
# tail. Kept well left of the right edge so the last candles are pure ambient noise.
_DECIDE = 0.80
_HOLD = 0.88
# Where the decision ramp crosses the level: before this the range is held to the line, after it a
# breakout label is free to trade through.
_BREAK_F = 0.78
# How far inside the level the range's designed tests sit, and the bounded peak of the candle texture.
# The depth must exceed the noise peak — texture alone must never fake a break — but only just: at
# 0.014 against a 0.005 peak the swing BODIES stopped 1.05-1.97% short of the line and the only contact
# was the planted graze wick, so the range read as respecting nothing. At 0.010 against 0.004 the bodies
# land 0.6-1.4% off it and the plateau's own wicks reach it, which is what a tested level looks like.
_TEST = 0.010
_NOISE = 0.004
# Each test is a short PLATEAU, not a single spike: a level is credible because price sat against it for
# a few bars and turned, and a lone bar grazing it is invisible among 130 candles. `_PLATEAU` is the
# half-width in window fractions, so a test spans roughly 2 x that.
_PLATEAU = 0.022
_TEST_F = (0.28, 0.50, 0.71)  # the three fractions at which the range comes back to the level
# Where the post-decision hold sits, as a log-distance from the level — the same for every label, and
# far enough out that the ambient tail's random walk (~1.1% stationary sd) cannot reach back across it.
_HOLD_D = 0.045


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

        def j(lo: float, hi: float) -> float:
            return float(rng.uniform(lo, hi))

        # EVERY control point is written as a distance INSIDE `gap` — the level is the one number the
        # whole picture is built from. The range used to wander an arbitrary distance below it (peaks at
        # a fixed 0.028 against a level 0.052-0.064 away), so the drawn line was 2.4-3.6% clear of every
        # candle and the range never once tested it: a line nothing respects reads as the wrong price,
        # whatever it says on it. Now the range TESTS the level twice by construction, which is what
        # makes it a level a learner can judge a break against.
        def inside(d: float) -> float:
            return gap - d

        def test_at(f: float) -> list[tuple[float, float]]:
            """A test of the level: price sits against it for a few bars, then turns away."""
            return [(f - _PLATEAU, inside(_TEST)), (f + _PLATEAU, inside(_TEST))]

        pts: list[tuple[float, float]] = [
            (0.00, inside(j(0.050, 0.062))),
            (0.10, inside(j(0.018, 0.028))),
            (0.19, inside(j(0.052, 0.064))),
            *test_at(_TEST_F[0]),
            (0.39, inside(j(0.054, 0.066))),
            *test_at(_TEST_F[1]),
            (0.61, inside(j(0.048, 0.060))),
            *test_at(_TEST_F[2]),  # the last touch before the decision
            (0.77, inside(j(0.016, 0.024))),
        ]
        # The decision at ~0.80, then a flat hold at the post-decision level (relative to `gap`). Every
        # label holds the SAME distance from the level, differing only in WHICH SIDE it holds on and
        # whether it poked through on the way: so the answer cannot be read off how far the right edge
        # sits from the line, and the ambient tail cannot wander back across it either (it used to, in
        # 4% of `no_break` seeds, printing the very breach the label denies).
        if target == "genuine_breakout":  # closes decisively beyond and holds beyond
            pts += [(_DECIDE, gap + 0.026), (_HOLD, gap + _HOLD_D), (1.00, gap + _HOLD_D)]
        elif target == "false_break":  # pokes beyond, then closes back inside and holds inside
            pts += [
                (_DECIDE, gap + 0.013), (0.84, gap + 0.011),
                (_HOLD, inside(_HOLD_D)), (1.00, inside(_HOLD_D)),
            ]
        elif target == "no_break":  # tests the level closer than ever before, and is rejected below
            pts += [(_DECIDE, inside(0.007)), (_HOLD, inside(_HOLD_D)), (1.00, inside(_HOLD_D))]
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown fakeout label {target!r}")

        shape = shape_from_points([(f, sign * y) for f, y in pts], n)
        # Peak texture stays a margin inside the smallest designed separation (no_break's 0.007), so
        # noise alone never crosses the level — the label is carried entirely by the designed shape.
        noise = bounded_noise(rng, n, amp=_NOISE)
        close_visible = base * np.exp(shape + noise)
        apply_ambient_tail(rng, close_visible)

        level_price = round(base * float(np.exp(sign * gap)), 2)
        kind = "resistance" if resistance else "support"
        if target == "no_break":
            # "Never traded beyond it" has to be exactly true, not true in most seeds: the ambient tail
            # is a random walk and the wick guard below can only clamp wicks, never the close path.
            clamp_close_inside(close_visible, level_price, kind)
        close_full = with_warmup(rng, close_visible)
        swing_kind = "high" if resistance else "low"
        decide_idx = WARMUP + resolve_swing(close_visible, int(_DECIDE * n), swing_kind)
        # Graze the extreme of each plateau AND its neighbour: a level touched by adjacent bars reads as
        # a level, where a single grazing wick reads as noise.
        test_idx = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), swing_kind, w=int(_PLATEAU * n)) + off
            for f in _TEST_F
            for off in (0, 1)
        )
        # `no_break` claims the level was never breached, so nothing in the window may trade beyond it —
        # not even a wick, which `build_series` draws at random and used to put through the line in 56%
        # of seeds, making the label indistinguishable from `false_break`. `false_break` breaks through
        # only during the decision: before and after it, the level holds (that reclaim IS the label).
        # `genuine_breakout` is free from the decision on, since holding beyond is what it claims.
        pre = (0, WARMUP + int(_BREAK_F * n))
        no_breach: tuple[tuple[int, int], ...]
        if target == "no_break":
            no_breach = ((0, len(close_full)),)
        elif target == "false_break":
            no_breach = (pre, (WARMUP + int(_HOLD * n), len(close_full)))
        else:
            no_breach = (pre,)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=decide_idx, kind="marker", label="test")],
            levels=[Level(price=level_price, label=kind, kind=kind)],
            level_guards=[
                LevelGuard(
                    price=level_price,
                    kind=kind,
                    tests=(*test_idx, decide_idx),
                    no_breach=no_breach,
                )
            ],
        )
