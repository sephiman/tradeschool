# SPDX-License-Identifier: AGPL-3.0-only
"""Whole-trade injector (module m24-l1): one setup with its four lines drawn on it.

m24-l1 narrates a complete trade in prose — a confluence level, a rejection wick below it, entry on the
close back above, a stop under the wick, a target at the prior high — and it is the most chart-shaped
lesson in the course. This injector draws that anatomy:

* ``long_setup`` — the level is tested twice as RESISTANCE, broken, the impulse prints the prior high,
  price pulls back to the old level (now support), pierces it with a rejection wick and closes back
  above. The close of that rejection bar is the entry; the stop sits just under the wick; the target is
  the prior high the impulse printed.

The role reversal the lesson teaches — "the old resistance becomes support" — is what earns the level
its corroboration honestly: the two pre-break touches are tests of a resistance, the pullback is a test
of a support, and the level ships one `LevelGuard` per role rather than an exemption.

Three of the four lines are `plan` levels: an entry, a stop and a target are prices the TRADER chose,
not prices the market has respected, so the "every drawn level was tested by the price action" contract
does not apply to them. They carry a stricter contract of their own instead (see
`tests/test_chart_annotations.py`): the entry IS the close of the entry bar, the target IS the prior
high, and the stop sits just below a rejection wick that is the deepest low of the whole setup.

Figure-only (the trade is fully resolved on screen, which is the opposite of what an exercise may
show), so the label is the visible state and the last-candle leak test does not apply.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
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

# Every price in the picture is written as a log distance from the CONFLUENCE LEVEL (offset 0) — the one
# number the whole trade is built from, exactly as the lesson builds it.
_TEST_F = (0.15, 0.31)  # the two touches of the level while it is still resistance
_PLATEAU = 0.020  # half-width of the flat at each touch, so the smoothing keeps price against the line
# How far INSIDE the level each touch's body stops, against the peak of the candle texture. The margin
# has to exceed the noise or a coil bar closes above the line the label says held — the same trade-off
# `fakeout` vets, at the same values: bodies land 0.4-1.2% short and the planted wick makes the contact.
_TEST_D = 0.008
# Where each guarded span ends. `_RESIST_UNTIL` stops short of the break ramp (a no-breach span that ran
# into the ramp would assert the level unbroken across the very bars that break it), and `_SUPPORT_FROM`
# starts once the close path is unambiguously above the level.
_RESIST_UNTIL = 0.37
_BREAK_F = 0.44  # the close beyond the level: from here it is support, not resistance
_SUPPORT_FROM = 0.48
_HIGH_F = 0.59  # the prior high the impulse prints — the target
_PULLBACK_F = 0.80  # price back at the level
_REACTION_F = 0.84  # the rejection bar: long wick through the level, close back above
_PRIOR_HIGH = 0.125  # how far above the level the impulse tops out
_ENTRY = 0.012  # the rejection bar's close, just above the level
# How far the rejection wick reaches BELOW the level, and how far under its tip the stop is parked. The
# pierce is deliberately deeper than any wick the coil can print (its bars are nearly flat, so
# `build_series` draws them short wicks), which is what keeps the rejection low the deepest of the setup
# and the stop line clear of the earlier action.
_PIERCE = 0.030
_STOP_MARGIN = 0.005
_NOISE = 0.004


class TradeAnatomyInjector(PatternInjector):
    name: ClassVar[str] = "trade_anatomy"
    labels: ClassVar[tuple[str, ...]] = ("long_setup",)
    hides_resolution: ClassVar[bool] = False  # the whole trade is on screen; nothing to leak
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target != "long_setup":  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown trade_anatomy label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        def coil(f: float) -> list[tuple[float, float]]:
            """A test of the level from below: price sits against it for a few bars, then backs off."""
            return [(f - _PLATEAU, -_TEST_D), (f + _PLATEAU, -_TEST_D)]

        pts: list[tuple[float, float]] = [
            (0.00, -0.012),
            (0.08, -0.010),
            *coil(_TEST_F[0]),
            (0.23, -0.016),
            *coil(_TEST_F[1]),
            (_RESIST_UNTIL, -0.014),
            (_BREAK_F, 0.020),  # the break: a full body beyond the level
            (0.51, 0.070),
            (_HIGH_F - 0.015, _PRIOR_HIGH),  # a short flat at the high so the smoothing keeps it
            (_HIGH_F + 0.015, _PRIOR_HIGH),
            (0.68, 0.062),
            (0.75, 0.024),
            (_PULLBACK_F, 0.007),  # back at the level: the setup is live
            (0.89, 0.018),
            (0.95, 0.024),
            (1.00, 0.026),
        ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        # The rejection bar's body is written after the smoothing (a crisp candle, not a smeared one):
        # it opens at the prior close and closes back above the level. Its wick is planted below.
        r = int(_REACTION_F * n)
        close_visible[r] = base * float(np.exp(_ENTRY))
        apply_ambient_tail(rng, close_visible)
        # Once the trade is live the level HELD — that is the premise the whole figure rests on, and the
        # ambient tail is a driftless walk that can wander through it over eight candles and print the
        # stop-out the picture denies. Only the closes are held; the rejection bar's wick is meant to
        # pierce, and it closes 1.2% above the line, well clear of this bound.
        clamp_close_inside(close_visible, round(base, 2), "support", start=int(_SUPPORT_FROM * n))
        # A quieter warm-up than the default. The warm-up's last bar is the first visible bar's OPEN, and
        # at the default sigma that join can start the chart below the rejection wick's tip — which would
        # put the stop line above the very first candle instead of under the deepest point of the setup.
        close_full = with_warmup(rng, close_visible, sigma=0.003)
        series = build_series(rng, close_full)

        level_price = round(base, 2)
        r_full = r + WARMUP
        tip = round(base * float(np.exp(-_PIERCE)), 2)
        series.low[r_full] = min(series.low[r_full], tip)
        # The entry is not a price this injector picks: it IS the close the rejection bar printed, read
        # back off the rendered series so the drawn line and the candle can never disagree.
        entry_price = series.close[r_full]
        # The target is the prior high the impulse actually printed — the extreme of the rendered wicks,
        # not the designed offset, for the same reason. Read over the VISIBLE window only: the warm-up is
        # a bridge pinned at its right end, so its left bars wander 10%+ from the chart and would hand the
        # target a price no candle on screen ever reached.
        target_price = round(max(series.high[WARMUP:r_full]), 2)
        stop_price = round(tip * (1.0 - _STOP_MARGIN), 2)

        pre_break = WARMUP + int(_RESIST_UNTIL * n)
        after_break = WARMUP + int(_SUPPORT_FROM * n)
        coil_tests = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), "high", w=int(_PLATEAU * n)) + off
            for f in _TEST_F
            for off in (0, 1)
        )
        # Only the pullback bar is a TEST of the level as support. The rejection bar is deliberately not
        # one: a test is a wick extended TO the line, and that bar's whole job is to go through it.
        pull_tests = (WARMUP + resolve_swing(close_visible, int(_PULLBACK_F * n), "low"),)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=r_full, kind="low", label="rejection")],
            levels=[
                Level(price=level_price, label="confluence", kind="support"),
                Level(price=entry_price, label="entry", kind="plan"),
                Level(price=stop_price, label="stop", kind="plan"),
                Level(price=target_price, label="target", kind="plan"),
            ],
            level_guards=[
                # The SAME price, guarded twice, because it plays both roles: a resistance the coil
                # tests and never closes beyond, then — once broken — a support the pullback tests and
                # only the rejection wick pierces. That is role reversal stated as a candle contract.
                LevelGuard(level_price, "resistance", tests=coil_tests, no_breach=((0, pre_break),)),
                LevelGuard(
                    level_price,
                    "support",
                    tests=pull_tests,
                    no_breach=((after_break, r_full), (r_full + 1, len(close_full))),
                ),
                # The rejection wick must be the deepest point of the setup, or the stop drawn just
                # under it would not be under the action at all: no other bar may trade below its tip.
                LevelGuard(tip, "support", no_breach=((0, r_full), (r_full + 1, len(close_full)))),
            ],
            candles_full=series,
            resolution_hint=1.0,
        )
