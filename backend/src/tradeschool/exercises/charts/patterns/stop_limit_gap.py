# SPDX-License-Identifier: AGPL-3.0-only
"""Stop-limit gap injector (module m21-l1): the protective order that never fills.

The central warning of m21-l1 is a sequence, not a state: a stop-limit's trigger sits at one price and
its limit just below, price slices through BOTH in a single fast candle, and the sell-limit is then
resting *above* the market — where nobody will lift it, because the market lets them buy lower. The
position stays open and keeps losing. That is hard to hold in prose and trivial to see on a chart.

* ``unfilled_stop_limit`` — price drifts down to the trigger, one candle's body crosses the trigger and
  the limit together, and from that bar on nothing ever trades back up to the limit again.

Both lines are `plan` levels: an order price is a price the TRADER chose, so the "every drawn level was
tested by the price action" contract does not apply. They carry a stricter contract instead (see
`tests/test_chart_annotations.py`): one bar's body must span both lines, and after it no bar's high may
reach the limit — the order's non-execution is a property of the candles, not of the caption.

The slice candle's close is written after the smoothing (a smeared drop over three bars is not a gap),
and the decline that follows is written directly rather than interpolated, so the path can never bounce
back through the limit on the way down. Classification injector: the label is the visible sequence.
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
    LEVEL_GRAZE,
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    clamp_close_inside,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# Every price is a log distance from the TRIGGER (offset 0).
# The real trap is usually a tick wide — trigger 100, limit 99.9 — which on a chart spanning ~15% is one
# line, not two. The gap is drawn a legible distance apart instead, and the caption says so: the tighter
# it really is, the worse the trap, so nothing about the lesson is softened by making it visible.
_LIMIT = -0.018
_SLICE_F = 0.72  # where the fast candle prints, well left of the ambient tail
_APPROACH_END = 0.012  # the last close before the slice: just above the trigger
_SLICE = 0.052  # the slice candle's own log drop — one body, through both lines
# Per-bar bleed after the slice: the position keeps losing, and no bounce comes. Kept moderate on purpose
# — a 20% collapse would squash both order lines into the top of the pane and undo the legibility the
# widened gap above is for.
_DRIFT = 0.0018
_UNFILLED_AT = 4  # bars after the slice where the "order unfilled" marker sits
_NOISE = 0.004


class StopLimitGapInjector(PatternInjector):
    name: ClassVar[str] = "stop_limit_gap"
    labels: ClassVar[tuple[str, ...]] = ("unfilled_stop_limit",)
    hides_resolution: ClassVar[bool] = False  # the whole sequence is on screen
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target != "unfilled_stop_limit":  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown stop_limit_gap label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        s = int(_SLICE_F * n)

        # The approach is built over its OWN window so the slice is never interpolated into: price
        # wanders above the trigger and comes down to just above it.
        pts = [
            (0.00, 0.055), (0.18, 0.042), (0.34, 0.050), (0.52, 0.030), (0.70, 0.036),
            (0.88, 0.020), (1.00, _APPROACH_END),
        ]
        approach = base * np.exp(shape_from_points(pts, s) + bounded_noise(rng, s, amp=_NOISE))

        # The slice: one candle from above the trigger to well below the limit, then a steady bleed. Both
        # are written directly — a control point would be smoothed into a three-bar slope, and a gap that
        # takes three bars is not the thing the lesson is warning about.
        m = n - s
        slice_close = approach[-1] * float(np.exp(-_SLICE))
        # The bleed is a clean decline plus BOUNDED texture, not a random walk. A walk's own dispersion
        # over thirty-odd candles is wider than the gap it just fell through, so it wanders back up to the
        # limit and prints the fill the lesson says never comes — the same reason `bounded_noise` exists.
        line = slice_close * np.exp(-_DRIFT * np.arange(m))
        after = line * np.exp(bounded_noise(rng, m, amp=0.010))
        after[0] = slice_close
        close_visible = np.concatenate([approach, after])
        apply_ambient_tail(rng, close_visible)

        trigger_price = round(base, 2)
        limit_price = round(base * float(np.exp(_LIMIT)), 2)
        # "The limit rests above the market" has to be exactly true, not true in most seeds, so the close
        # path is held below the line as well as designed below it (the same guarantee `no_break` makes
        # about its own level, for the same reason: a guard can only move wicks).
        clamp_close_inside(close_visible, limit_price, "resistance", start=s + 1)
        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        s_full = WARMUP + s
        # A resting sell-limit fills the moment price TOUCHES it, so "unfilled" is a strictly-below claim
        # about every bar after the slice — and that is one a `LevelGuard` cannot make: a guard clamps a
        # breaching wick back TO the line, and a wick that reaches the limit is a fill. So the cap is
        # planted in the candles here, a graze under the line. The clamp above keeps the closes further
        # under it still, which is what stops this cap from ever cutting into a body.
        cap = round(limit_price * (1.0 - LEVEL_GRAZE), 2)
        for j in range(s_full + 1, len(series.close)):
            series.high[j] = min(series.high[j], cap)

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[
                Annotation(index=s_full, kind="low", label="gap"),
                Annotation(index=min(s_full + _UNFILLED_AT, len(close_full) - 1), kind="high",
                           label="unfilled"),
            ],
            levels=[
                Level(price=trigger_price, label="trigger", kind="plan"),
                Level(price=limit_price, label="limit", kind="plan"),
            ],
            level_guards=[
                # Before the slice the trigger is untouched — a stop that had already been reached would
                # not still be resting — and the last approach bar comes down to it, so the trigger is a
                # price the chart shows price arriving at rather than a number in empty space.
                LevelGuard(trigger_price, "support", tests=(s_full - 1,), no_breach=((0, s_full),)),
                # After the slice the LIMIT is the line the market never trades back up to. That is the
                # whole lesson: the order rests above the market, unfilled, while the loss runs. The wick
                # cap planted above already enforces it; this states it in the shared contract too, so a
                # future change to the candles cannot quietly drop the claim.
                LevelGuard(limit_price, "resistance", no_breach=((s_full + 1, len(close_full)),)),
            ],
            candles_full=series,
            resolution_hint=-1.0,
        )
