# SPDX-License-Identifier: AGPL-3.0-only
"""Origin-zone injector (module m30-l1): what the SMC dialect calls an "order block".

The mechanic the course already taught, under two other names. m08-l1 explains a support as *a shelf of
resting buy orders* the last visits taught people to leave, and a genuine break as role reversal — the
level that capped price now holds it. m09 explains a large buyer who cannot fill in one go and absorbs
supply across a whole range. Put those together and the origin zone falls out: the **last opposing
candles before the impulse that broke structure** are where the size that caused the impulse was working,
it could not all get filled there, and a return often finds the remainder.

So the geometry this plants is a sequence, not a shape:

  a range whose high is tested twice  ->  a dip (the ORIGIN)  ->  an impulse that closes clean past that
  high (the BOS)  ->  a return into the dip  ->  and what the return does.

* ``zone_respected`` — the return wicks into the zone, closes above it, and price leaves upward.
* ``zone_failed``    — the return closes clean through the zone and keeps going. Zones fail; a lesson
  that only ever showed them holding would be teaching the dogma rather than the mechanic.
* ``no_zone``        — the same dip and the same return, but the rally between them **never took out the
  prior high**. Nothing broke, so there is no origin zone: this is the characteristic error (calling any
  pullback an order-block retest) given its own label instead of a footnote.

All three share their opening two thirds bar for bar, which is deliberate: the reading that separates
them is *did structure break*, and that is only a fair question when nothing else differs.

**Every label is BULLISH, deliberately.** The break is always of a HIGH and the zone is always demand, in
all three labels and on every seed. That is a content decision, not an oversight: m30-l1 and m30-ex-1 both
state the bullish case in words ("a close clean past the high the range had been testing"), and a bearish
seed served under those prompts would be graded against a question that describes the mirror of what is on
screen. The mechanic is symmetric and the lesson says so in prose; what is not symmetric is the generated
set. If a bearish variant is ever added here, `test_chart_bands.py::test_origin_zone_only_ever_plants_the
_bullish_case` fails until the prompts and the lesson are made symmetric in BOTH languages — which is the
order those two changes have to happen in.

The shaded `Band` is GROUND TRUTH — drawing it would answer the question — so it reaches the learner
only after grading, and the figure. `hides_resolution` is True: like `fakeout`, the decision is on screen
but what follows it is not, and the ambient tail is what keeps the last candles from betraying the label.

Candles are built here (`candles_full`) because the band IS the origin candles' own range: it has to be
read off the wicks a learner sees, not off the close path the dip was designed in.
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
    """[lo, hi) — the last down-leg before the impulse, in the series' own coords. The zone is its range.

    The definition applied rather than approximated: the origin zone is *the last opposing candles before
    the move*, so the window runs from the local high that leg started at down to the low it ended on.

    Anchoring on that high, rather than on a fixed window around the low or on a walk back through
    consecutive bearish closes, is what keeps the zone's WIDTH honest at both ends. A fixed three-bar
    window collapsed to a 0.17%-wide hairline whenever the noise flattened those three candles, and a
    walk back through bearish closes ran 6% wide whenever the noise chained the dip onto the range's own
    descent — a "zone" that size is a downtrend. The high is always strictly before the low, so the
    window is at least two candles wide by construction.
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
