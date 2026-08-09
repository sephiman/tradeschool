# SPDX-License-Identifier: AGPL-3.0-only
"""Multi-timeframe injector (m20-l2): ONE stretch of price, drawn twice at two resolutions.

The only injector that returns a second candle panel. Every other one plants a feature and asks what
it is; this one plants a RELATIONSHIP BETWEEN TWO PANELS — what the lower frame is doing *inside* the
higher one — which is unanswerable with a single chart on screen.

The higher frame is never generated. It is `aggregate`d out of the lower one, bar for bar: first open,
last close, extreme high, extreme low, summed volume. That is m20-l2's opening claim ("one 4h candle IS
four 1h candles — aggregation, not new information") made literally true of the chart that teaches it,
and `tests/test_chart_timeframes.py` re-derives it to the cent from the published lower panel.

Two label families over one geometry, the `converging_lines` precedent:

* WHAT THE LOWER FRAME IS DOING — `pullback_against_trend` (the 15m "trend" that is a 4h pullback, the
  error the lesson is named for), `continuation_with_trend`, and `higher_frame_ranges` as the control
  that makes "against the higher frame" a claim an answer can be wrong about.
* WHICH PANEL CONTAINS THE OTHER — `top_is_higher_frame` / `bottom_is_higher_frame`: the same two
  panels with the aggregate drawn above or below. Only its POSITION moves, so the answer is read off
  the candles (the same path in fewer bars) and off nothing else.

Bidirectional from birth, like every family since m31: `rng` mirrors the whole construction, so a
pullback inside a downtrend is as ordinary here as one inside an uptrend.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    ContextPanel,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    apply_ambient_tail,
    bounded_noise,
    candle_extreme,
    shape_from_points,
)
from tradeschool.exercises.charts.types import Series

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

#: Lower-frame bars per higher-frame bar. Four, not the sixteen of the lesson's 15m -> 4h arithmetic: a
#: readable pair of panels needs a coarse frame with bars left in it, and at sixteen a 160-bar window
#: aggregates to ten candles. 1h -> 4h is the same claim at a ratio a chart can actually show.
RATIO = 4
#: Warm-up, and the ONE place this injector departs from `common.WARMUP`'s 30. It has to be a whole
#: number of higher-frame bars, or the aggregate cannot be trimmed at the instant the lower frame is
#: and the two panels would start at different moments — which is the one thing the figure denies.
WARMUP = 32

#: Peak candle texture, as a fraction of price. Large next to the other injectors' 0.3%, and
#: deliberately: the upper frame's wicks ARE the lower frame's excursions, so a path too smooth to
#: wander inside its own group aggregates into four bars of one colour and a candle with no wicks.
_NOISE = 0.010
_AMPLITUDE = (0.85, 1.15)  # per-seed scaling of the whole shape, so no two windows travel the same

#: Each shape as (control points in log-offset, where the lower-frame run BEGINS, what that pivot is
#: for a positive amplitude). The pivot fraction is not decoration: it is what the tests measure the
#: run from, and what the reader's eye is drawn to once the answer is revealed.
#:
#: Read them as higher-frame structures. `pullback_against_trend` is an impulse with two intermediate
#: pullbacks — so the upper frame has a ladder, not a straight line — and then a retracement of ~40% of
#: it, which is deep enough to look like a trend on the lower frame and shallow enough to leave the
#: upper structure intact (the last leg ends well above the previous higher low).
_SHAPES: dict[str, tuple[list[tuple[float, float]], float, str]] = {
    "pullback_against_trend": (
        [(0.00, 0.000), (0.10, 0.035), (0.18, 0.020), (0.30, 0.075), (0.40, 0.058),
         (0.55, 0.130), (0.62, 0.112), (0.72, 0.185), (0.80, 0.152), (0.88, 0.128),
         (0.96, 0.114), (1.00, 0.112)],
        0.72, "high",
    ),
    "continuation_with_trend": (
        [(0.00, 0.000), (0.10, 0.030), (0.18, 0.014), (0.32, 0.070), (0.42, 0.052),
         (0.55, 0.105), (0.64, 0.086), (0.72, 0.130), (0.82, 0.165), (0.92, 0.196),
         (1.00, 0.210)],
        0.64, "low",
    ),
    # The control: the upper frame goes nowhere, so the lower-frame run is neither with a trend nor
    # against one. Its legs are the same SIZE as the pullback above — what differs is that they keep
    # cancelling, which is the only honest way to tell a range from a trend.
    "higher_frame_ranges": (
        [(0.00, 0.000), (0.08, 0.045), (0.20, -0.040), (0.32, 0.048), (0.44, -0.045),
         (0.56, 0.046), (0.68, -0.042), (0.80, 0.044), (0.92, -0.020), (1.00, -0.012)],
        0.80, "high",
    ),
}
_SHAPE_LABELS = tuple(_SHAPES)
#: The second family. Both draw one of the shapes above at random — the question is not what the price
#: is doing, it is which of the two panels is the aggregation of the other.
_POSITION_LABELS = ("top_is_higher_frame", "bottom_is_higher_frame")


def aggregate(lower: Series, ratio: int = RATIO) -> Series:
    """The higher frame: every bar the exact aggregation of `ratio` lower ones.

    First open, last close, extreme high, extreme low, summed volume — the definition of a candle at a
    coarser resolution, and the whole of what a timeframe change does. Computed from the ROUNDED lower
    values (the ones the payload publishes), so the equality the tests assert is exact to the cent
    rather than exact-up-to-rounding.

    A trailing partial group is dropped: a forming candle is a real thing on a real chart, but here it
    would be the one bar that is not the aggregation of `ratio` others.
    """
    groups = len(lower.close) // ratio
    time, open_, high, low, close, volume = [], [], [], [], [], []
    for g in range(groups):
        lo, hi = g * ratio, (g + 1) * ratio
        time.append(lower.time[lo])
        open_.append(lower.open[lo])
        high.append(max(lower.high[lo:hi]))
        low.append(min(lower.low[lo:hi]))
        close.append(lower.close[hi - 1])
        volume.append(round(sum(lower.volume[lo:hi]), 2))
    return Series(time=time, open=open_, high=high, low=low, close=close, volume=volume)


def _with_warmup(rng: np.random.Generator, close_visible: np.ndarray) -> np.ndarray:
    """`common.with_warmup`, at this injector's own WARMUP — see the constant for why it differs."""
    walk = np.cumsum(rng.normal(0.0, 0.008, WARMUP + 1))
    walk = walk - walk[-1]  # end the warm-up at ~close_visible[0]
    warm = close_visible[0] * np.exp(walk[:WARMUP])
    return np.concatenate([warm, close_visible])


class MultiTimeframeInjector(PatternInjector):
    name: ClassVar[str] = "multi_timeframe"
    labels: ClassVar[tuple[str, ...]] = (*_SHAPE_LABELS, *_POSITION_LABELS)
    #: The label IS the visible state — what the two panels already show — so the anti-leak test does
    #: not apply and the credibility test is the gate (see `base`).
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in self.labels:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown multi_timeframe label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        sign = 1.0 if rng.integers(0, 2) else -1.0
        # Whole groups only, so every upper bar has its full complement of lower ones (see `aggregate`).
        bars = n - (n % RATIO)

        shape_name = target if target in _SHAPES else str(rng.choice(_SHAPE_LABELS))
        points, turn_f, turn_kind = _SHAPES[shape_name]
        amp = sign * float(rng.uniform(*_AMPLITUDE))
        shape = shape_from_points([(f, amp * y) for f, y in points], bars)
        close_visible = base * np.exp(shape + bounded_noise(rng, bars, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)
        close_full = _with_warmup(rng, close_visible)

        lower = build_series(rng, close_full)
        upper = aggregate(lower, RATIO)

        # Where the lower-frame run starts, read off the CANDLES: a reader sees the pivot on the wick
        # that made it, and it is what turns "the last stretch" into a bar index the contract can use.
        if amp < 0:
            turn_kind = "low" if turn_kind == "high" else "high"
        half = max(2, int(0.03 * bars))
        turn = candle_extreme(
            lower, WARMUP + int(turn_f * bars) - half, WARMUP + int(turn_f * bars) + half, turn_kind
        )

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=turn, kind=turn_kind, label="turn")],
            candles_full=lower,
            context=ContextPanel(
                series=upper,
                ratio=RATIO,
                # Context above, trigger below — the sequence m20-l2 teaches — for every label except
                # the one whose whole question is "and what if it is not?".
                position="below" if target == "bottom_is_higher_frame" else "above",
            ),
            # The higher frame is what the resolution obeys, which is the lesson in one number: a
            # pullback ends and the trend that contained it resumes, so both trending shapes continue
            # WITH the upper frame and the range continues nowhere.
            resolution_hint=0.0 if shape_name == "higher_frame_ranges" else sign,
        )

    def figure_context(self, close_full: np.ndarray, series: Series) -> Series:
        """The aggregate recomputed over the EXTENDED series (`figure_overlays`' precedent).

        A figure appends a resolution leg to the lower frame; an aggregate built before that leg would
        stop where the exercise window did, leaving the upper panel blank across exactly the stretch
        the figure exists to show.
        """
        del close_full  # the aggregation is a function of the CANDLES, not of the close path
        return aggregate(series, RATIO)
