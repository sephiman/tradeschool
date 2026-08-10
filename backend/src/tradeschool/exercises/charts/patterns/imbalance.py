# SPDX-License-Identifier: AGPL-3.0-only
"""Imbalance injector (m34-l1): what the SMC dialect calls a "fair value gap" (FVG).

Plants the standard three-candle detector: bar *i*'s high below bar *i+2*'s low, so exactly one candle
crossed the span. Every chart carries at most one — `_close_stray_gaps` repairs incidental gaps, so the
question has a single subject.

Every label is BULLISH, deliberately — the same decision `origin_zone` documents, guarded by
`test_chart_bands.py::test_imbalance_only_ever_plants_the_bullish_case`. `gap_spans` still detects both
directions, since a chart must be provably free of a gap in *either*.

Candles are planted (`candles_full`) because the gap's edges ARE two specific wicks: at the impulse bar,
the volatility `build_series` derives is large enough to swallow the whole gap.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    Band,
    LevelGuard,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    clamp_close_inside,
    shape_from_points,
    with_warmup,
)
from tradeschool.exercises.charts.types import Series

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

_IMPULSE_F = 0.44  # where the fast move sits, as a window fraction
_JUMP = 0.055  # the move, in log price — carried by ONE bar for the two imbalance labels
_GAP_LOW = 0.012  # the pre-impulse bar's high: the gap's lower edge, and the ceiling the range coils under
_GAP_HIGH = 0.045  # the post-impulse bar's low: its upper edge. A ~4% span — a zone, not a hairline.
_NOISE = 0.003

# Everything before the move. Flat into it, so the impulse bar's own body carries the whole jump rather
# than sharing it with a smoothed ramp (which would drag the gap's lower edge up into the span).
# Every point at or below 0, so the range coils UNDER the span the impulse is about to skip. Without that,
# an early bar's high poked above `_GAP_LOW` and sat inside the published zone — which would have the chart
# show a "span almost nothing traded in" that the range had, in part, already traded in.
_PRE: tuple[tuple[float, float], ...] = (
    (0.00, -0.002), (0.12, -0.010), (0.24, -0.001), (0.36, -0.006), (_IMPULSE_F, 0.000),
)
# After the move. For the two planted labels these are offsets from the PRE level and the `_JUMP` step is
# added on top, so the ABSOLUTE offset of each point is its value + 0.055 — the comment on each line gives
# that absolute figure, because what matters is where the path sits relative to the gap at [0.004, 0.045].
# `no_imbalance` takes no step, so its values are already absolute.
_POST: dict[str, tuple[tuple[float, float], ...]] = {
    "imbalance_unfilled": (
        (0.56, 0.030),  # 0.085 — the move extends
        (0.68, 0.008),  # 0.063
        (0.76, 0.000),  # 0.055 — the deepest pullback: a full 1% clear of the gap's upper edge, so the
        #                 gap is left untouched by any wick (and an undrawn guard holds the tail to it)
        (0.88, 0.012),  # 0.067
        (1.00, 0.020),  # 0.075
    ),
    "imbalance_filled": (
        (0.56, 0.030),  # 0.085
        (0.68, -0.025),  # 0.030 — into the span
        (0.78, -0.070),  # -0.015 — and clean out the bottom of it: the gap is filled, visibly
        (0.88, -0.030),  # 0.025
        (1.00, 0.000),  # 0.055 — recovered above the span it just traded through
    ),
    # The same size of move, walked up over several OVERLAPPING candles, so no span is crossed in one bar.
    "no_imbalance": (
        (0.455, 0.028), (0.47, 0.055), (0.56, 0.078), (0.68, 0.062), (0.78, 0.048), (1.00, 0.060),
    ),
}
# A three-candle gap has to be worth a name before a chart may claim one, and `no_imbalance` has to be
# free of anything that big. 1.2% of price is the floor: wide enough to read as a zone on screen, narrow
# enough that the repair pass leaves ordinary candle texture alone.
GAP_FLOOR = 0.012


def gap_spans(series: Series, lo: int, hi: int) -> list[tuple[int, float, float]]:
    """Every three-candle imbalance in `[lo, hi)`, both directions: (first bar, span low, span high).

    The one definition the injector plants, the repair pass removes and the tests measure.
    """
    out: list[tuple[int, float, float]] = []
    for i in range(max(0, lo), min(hi, len(series.close) - 2)):
        up = series.low[i + 2] - series.high[i]
        down = series.low[i] - series.high[i + 2]
        if up > GAP_FLOOR * series.close[i]:
            out.append((i, series.high[i], series.low[i + 2]))
        elif down > GAP_FLOOR * series.close[i]:
            out.append((i, series.high[i + 2], series.low[i]))
    return out


def _close_stray_gaps(series: Series, keep: int | None) -> None:
    """Remove every gap but `keep`'s, extending the earlier bar's WICK to where the later bar traded.

    Only ever lengthens a wick — the same restriction `apply_level_guards` works under.
    """
    for i in range(len(series.close) - 2):
        if i == keep:
            continue
        if series.low[i + 2] - series.high[i] > 0.0:
            series.high[i] = round(series.low[i + 2], 2)
        elif series.low[i] - series.high[i + 2] > 0.0:
            series.low[i] = round(series.high[i + 2], 2)


class ImbalanceInjector(PatternInjector):
    name: ClassVar[str] = "imbalance"
    labels: ClassVar[tuple[str, ...]] = ("imbalance_unfilled", "imbalance_filled", "no_imbalance")
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in _POST:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown imbalance label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        planted = target != "no_imbalance"

        shape = shape_from_points([*_PRE, *_POST[target]], n)
        g = int(_IMPULSE_F * n)  # the impulse bar, in visible coords
        if planted:
            # A true one-bar move: a Heaviside step, not a control point. `shape_from_points` smooths over
            # three bars, so any step expressed as a control point would be walked up over ~3 candles —
            # which is precisely the `no_imbalance` chart, and the opposite of what these two labels claim.
            shape = shape.copy()
            shape[g:] += _JUMP
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)
        if target == "imbalance_unfilled":
            # "Still open" is a claim about every candle after the gap, and two things can break it. The
            # ambient tail is a driftless walk that wandered a BODY into the span in 9% of seeds — and a
            # body is the close path, which no guard may move, so it has to be bounded here. Once every
            # body sits above the span, the undrawn `LevelGuard` below can do its half of the job: it
            # clamps a stray WICK back to the gap's upper edge, which it could not do while a body was
            # already inside (`apply_level_guards` never moves a wick past its own candle's body).
            clamp_close_inside(
                close_visible, base * float(np.exp(_GAP_HIGH)), "support", start=g + 2
            )
        close_full = with_warmup(rng, close_visible)
        if planted:
            # Hold every close before the impulse under the zone's floor. The designed range already sits
            # there, but the WARM-UP does not have to: `with_warmup` pins its last step at the visible
            # open and the step before it is a free draw, so the first visible bar — which opens at the
            # last warm-up close — could open up to 2% above the floor, putting its BODY inside the zone.
            # A guard cannot fix that (it never moves a wick past its own candle's body), so it is bounded
            # here, on the close path, before the candles are derived from it.
            ceiling = base * float(np.exp(_GAP_LOW)) * (1.0 - 0.0015)
            np.minimum(close_full[: WARMUP + g], ceiling, out=close_full[: WARMUP + g])
        series = build_series(rng, close_full)

        w_g = WARMUP + g
        bands: list[Band] = []
        annotations: list[Annotation] = []
        guards: list[LevelGuard] = []
        if planted:
            # The two edges, planted. `max`/`min` against the body: a wick may be lengthened, never
            # shortened past the candle's own open/close (the rule `apply_level_guards` works under too).
            body_high = max(series.open[w_g - 1], series.close[w_g - 1])
            body_low = min(series.open[w_g + 1], series.close[w_g + 1])
            series.high[w_g - 1] = round(max(body_high, base * float(np.exp(_GAP_LOW))), 2)
            series.low[w_g + 1] = round(min(body_low, base * float(np.exp(_GAP_HIGH))), 2)
            _close_stray_gaps(series, keep=w_g - 1)
            low, high = series.high[w_g - 1], series.low[w_g + 1]
            bands = [Band(low=low, high=high, label="imbalance", kind="imbalance")]
            annotations = [Annotation(index=w_g, kind="marker", label="imbalance")]
            # The range coils UNDER the span, by contract rather than by luck: an earlier bar whose wick
            # poked above the floor would put range price action inside a zone that claims almost nothing
            # traded in it, and on one seed in a hundred a single 3.8% wick ate the zone down to 0.65% of
            # price. Undrawn, like the guard below — the band is not a line, but its floor still owes the
            # candles a contract. Bodies here are all below the floor, so this only ever moves wicks.
            guards = [LevelGuard(low, "resistance", no_breach=((0, w_g),))]
            if target == "imbalance_unfilled":
                # The gap stays open — a claim about every bar that follows, and the ambient tail is a
                # driftless walk that can wander into it. An UNDRAWN guard (no `Level` accompanies it):
                # the band is not a line, but its upper edge still owes the candles a contract, and this
                # is the same machinery every drawn level uses. `test_chart_bands.py` checks it, since
                # `test_chart_levels.py` discovers its targets from published levels and cannot see this.
                guards.append(LevelGuard(high, "support", no_breach=((w_g + 2, len(close_full)),)))
            else:
                revisit = next(
                    (
                        i
                        for i in range(w_g + 2, len(close_full))
                        if series.low[i] < low  # traded clean through the whole span
                    ),
                    None,
                )
                if revisit is not None:
                    annotations.append(Annotation(index=revisit, kind="low", label="revisit"))
        else:
            _close_stray_gaps(series, keep=None)
            annotations = [Annotation(index=w_g + 2, kind="marker", label="traded_through")]

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            bands=bands,
            level_guards=guards,
            candles_full=series,
            # The figure runs `imbalance_unfilled` and lets the appended leg BE the revisit — the gap is
            # a magnet, and an exercise stops before it comes back. Hence a downward resolution here.
            resolution_hint=-1.0 if target == "imbalance_unfilled" else 1.0,
        )
