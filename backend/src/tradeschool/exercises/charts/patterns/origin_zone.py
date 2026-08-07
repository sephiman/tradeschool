# SPDX-License-Identifier: AGPL-3.0-only
"""Origin-zone injector (m30-l1): what the SMC dialect calls an "order block".

Plants a sequence, not a shape: a range whose high is tested twice -> a dip (the ORIGIN) -> an impulse
closing clean past that high (the BOS) -> a return into the dip -> what the return does. All labels
share their opening two thirds bar for bar, so only *did structure break* separates them.

Every label is BULLISH, deliberately: m30-l1 and m30-ex-1 state the bullish case in words, so a
bearish seed would be graded against a prompt describing its mirror. Adding one fails
`test_chart_bands.py::test_origin_zone_only_ever_plants_the_bullish_case` until the prompts and the
lesson are made symmetric in BOTH languages — in that order.

Candles are built here (`candles_full`) because the band IS the origin candles' own range: it must be
read off the wicks the learner sees, not the close path the dip was designed in.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    Band,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    LEVEL_GRAZE,
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    candle_extreme,
    clamp_close_inside,
    shape_from_points,
    with_warmup,
)
from tradeschool.exercises.charts.types import Series

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# Log offsets from the ORIGIN ZONE's own price (offset 0), which is what `base` means here: the zone is
# the anchor the whole picture is built from, the way the shelf is for `liquidity_sweep`.
_PRIOR_HIGH = 0.065  # the range high the impulse has to take out for there to be a break at all
_IMPULSE_TOP = 0.115  # a close 5% clear of that high — a BOS nobody has to squint at
_FAILED_TOP = 0.022  # `no_zone`'s rally: 4.3% short of the prior high, past any wick draw
_RETEST = 0.004  # where the return CLOSES: inside the zone but well above its far edge, which is the
#                  side of the line m08-l1 puts between a level tested and a level lost
_OUTCOME = 0.080  # how far the outcome travels from the zone — the SAME distance for both sides, so
#                   the label is readable off which side price ended on and never off a ruler.

# The shared opening: the range, its two tests of the high, and the dip that becomes the zone.
_PREFIX: tuple[tuple[float, float], ...] = (
    (0.00, 0.030),
    (0.08, _PRIOR_HIGH), (0.14, _PRIOR_HIGH),  # first test of the high (a plateau, so it reads as one)
    (0.22, 0.008),
    (0.30, _PRIOR_HIGH), (0.36, _PRIOR_HIGH),  # second test: now it is structure, not an accident
    (0.44, 0.002),
    (0.47, -0.005),  # the dip: the last opposing candles before the move
    (0.50, 0.003),
)
# Per label: the rally out of the zone, the return, and the outcome.
_LEGS: dict[str, tuple[tuple[float, float], ...]] = {
    "zone_respected": (
        (0.60, 0.080), (0.66, _IMPULSE_TOP), (0.72, 0.098),
        (0.80, _RETEST),
        (0.87, 0.032), (0.94, 0.062), (1.00, _OUTCOME),
    ),
    "zone_failed": (
        (0.60, 0.080), (0.66, _IMPULSE_TOP), (0.72, 0.098),
        (0.80, _RETEST),
        (0.87, -0.045), (0.94, -0.068), (1.00, -_OUTCOME),
    ),
    "no_zone": (
        (0.60, 0.016), (0.66, _FAILED_TOP), (0.72, 0.014),
        (0.80, _RETEST),
        (0.87, 0.014), (0.94, 0.020), (1.00, 0.026),
    ),
}
_ORIGIN_F = 0.47  # where the dip bottoms, as a window fraction
_ORIGIN_SEARCH = 0.05  # how far either side of that to look for the actual candle low
_ORIGIN_LOOKBACK = 5  # the last few candles before the impulse; more than that is a downtrend, not a zone
_RETEST_F = 0.80
_NOISE = 0.003  # peak texture, well inside every designed separation above


def _origin_bars(series: Series, low_bar: int) -> tuple[int, int]:
    """[lo, hi) — the last down-leg before the impulse. The zone is its range.

    Anchored high-to-low, not on a fixed window (collapses to a hairline) or a walk back through
    bearish closes (runs 6% wide, which is a downtrend, not a zone).
    """
    lo = candle_extreme(series, max(0, low_bar - _ORIGIN_LOOKBACK), low_bar, "high")
    return lo, low_bar + 1


class OriginZoneInjector(PatternInjector):
    name: ClassVar[str] = "origin_zone"
    labels: ClassVar[tuple[str, ...]] = ("zone_respected", "zone_failed", "no_zone")
    hides_resolution: ClassVar[bool] = True  # the decision is on screen; what follows it is not
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in _LEGS:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown origin_zone label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        shape = shape_from_points([*_PREFIX, *_LEGS[target]], n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        retest = int(_RETEST_F * n)
        apply_ambient_tail(rng, close_visible)
        if target == "zone_respected":
            # The zone HELD, so no close may end up under it. The dip's own wick sets the zone's floor and
            # the ambient tail is a driftless walk, so "held" is only reliably true if the close path
            # itself is bounded above the zone's price from the return on — after the tail is applied,
            # since the tail is exactly what would otherwise wander through it (`clamp_close_inside`).
            clamp_close_inside(close_visible, round(base, 2), "support", start=retest)
        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        search = max(2, int(_ORIGIN_SEARCH * n))
        centre = WARMUP + int(_ORIGIN_F * n)
        low_bar = candle_extreme(series, centre - search, centre + search + 1, "low")
        w_lo, w_hi = _origin_bars(series, low_bar)
        w_retest = WARMUP + retest
        broke = target != "no_zone"

        bands: list[Band] = []
        annotations: list[Annotation] = []
        if broke:
            zone_low = round(min(series.low[w_lo:w_hi]), 2)
            zone_high = round(max(series.high[w_lo:w_hi]), 2)
            bands = [Band(low=zone_low, high=zone_high, label="origin", kind="origin")]
            # The return has to actually TRADE into the zone — "price came back to the block" is the
            # claim, and a return that stops a hair short of it is a different (and commoner) chart.
            # Planted like `liquidity_sweep`'s sweep wick. What "respected" then means is the honest
            # version, not the tidy one: price trades INSIDE the band — the close often lands there too,
            # since the band spans the whole down-leg — and what it may not do is close under the FAR
            # edge, which is where m08-l1 puts the line between a level tested and a level lost.
            series.low[w_retest] = round(min(series.low[w_retest], zone_high * (1.0 - LEVEL_GRAZE)), 2)
            prior_high = max(series.high[WARMUP:w_lo])
            bos = next(
                (i for i in range(w_hi, WARMUP + n) if series.close[i] > prior_high),
                None,
            )
            annotations = [
                Annotation(index=low_bar, kind="low", label="origin"),
                *([Annotation(index=bos, kind="high", label="BOS")] if bos is not None else []),
                Annotation(index=w_retest, kind="low", label="retest"),
            ]
        else:
            # Nothing broke, so nothing is marked as an origin: what IS marked is the rally that failed
            # to take the high out, because that absence is the whole answer.
            annotations = [
                Annotation(
                    index=candle_extreme(series, WARMUP + int(0.60 * n), WARMUP + int(0.72 * n), "high"),
                    kind="high",
                    label="failed_break",
                )
            ]

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            bands=bands,
            candles_full=series,
            resolution_hint=1.0 if target == "zone_respected" else -1.0,
        )
