# SPDX-License-Identifier: AGPL-3.0-only
"""Diagonal geometry and its respect contract (m31) — the moving-level twin of `Level`/`LevelGuard`.

One definition of "the line's price at bar i", shared by the two injectors that draw diagonals, the
figure builder that projects them through the appended resolution, and `tests/test_chart_diagonals.py`
that measures whether the candles honour them. A second, private copy of that arithmetic is exactly how
a drawn line and its contract drift apart.

**Respect is measured on the CLOSE**, never on the wick. That is not a convenience: m31-l1 teaches that
a wick through a diagonal is even less information than a wick through a horizontal level, so a contract
that failed on wicks would enforce the opposite of what the lesson says. It is also why there is no
`DiagonalGuard` — nothing here ever moves a candle. The contract is asserted over hundreds of seeds, the
way a `Band`'s is, not enforced by mutation the way a `Level`'s is.
"""

from __future__ import annotations

import numpy as np

from tradeschool.exercises.charts.patterns.base import Diagonal
from tradeschool.exercises.charts.types import Series

#: A close within this fraction of the line counts as sitting ON it — the thickness of the pencil.
#: Diagonals are drawn by hand and by eye, so an exact-touch criterion would describe no real trendline.
TOUCH_MARGIN = 0.008
#: ...and a close this far past the line counts as through it rather than as slop.
BREACH_MARGIN = 0.004
# Both are MEASURED bounds, not traced ones — the same discipline that put m30's clean-break margin at
# 2% after measuring a 3.40% floor over 600 samples.
#
# TOUCH_MARGIN, over 12,000 designed visits (600 seeds x 5 `trend_channel` labels x 4 visits): the
# CLOSEST bar of a visit lands 0.194% from the line at the median, 0.467% at the 99th percentile and
# 0.572% at the worst. A channel's parallel, over 3,600 more, tops out at 0.623%. So 0.8% clears the
# measured worst case by ~40% — a bound with headroom, not the observed maximum rounded up. And the
# headroom is the whole of it: at 0.6% every visit is still counted, at 0.4% one in twenty is lost and
# at 0.3% one in five, which is what a line the contract can no longer call validated looks like.
#
# BREACH_MARGIN, over the same sweep: no close ever gets on the wrong side of a line its label says
# held — the worst is -0.043%, i.e. still inside. That is not luck, it is `clamp_close_inside` below,
# added after a sweep WITHOUT it put a body 0.117% through a `line_holds` line on one seed in 300. So
# 0.4% is not slack the generator needs; it is how far an EDIT would have to move the price action
# before the contract stops calling the line respected.
# `tests/test_chart_diagonals.py` re-measures both on every run rather than trusting these numbers.


def price_at(d: Diagonal, index: int) -> float:
    """The line's price at `index`, in FULL-series coords. Extrapolates freely past both anchors."""
    span = d.end - d.start
    if span == 0:
        return d.start_price
    return d.start_price + (d.end_price - d.start_price) * (index - d.start) / span


def projected(d: Diagonal, lo: int, hi: int) -> np.ndarray:
    """`price_at` over `[lo, hi)`, vectorised."""
    return np.array([price_at(d, i) for i in range(lo, hi)], dtype=float)


def extended(d: Diagonal, end: int) -> Diagonal:
    """The same line, re-anchored to reach `end` — what a figure's appended resolution needs.

    The *line* is unchanged (`price_at` gives identical answers); only how far it is drawn moves, which
    is what "the projected line" means in the prose.
    """
    return Diagonal(
        start=d.start,
        end=end,
        start_price=d.start_price,
        end_price=price_at(d, end),
        label=d.label,
        kind=d.kind,
    )


def _signed_excursion(closes: np.ndarray, line: np.ndarray, kind: str) -> np.ndarray:
    """How far each close sits BEYOND the line, as a fraction of the line. Negative = inside."""
    beyond = (closes - line) if kind == "resistance" else (line - closes)
    return np.asarray(beyond / line, dtype=float)


#: Bars a run of near-line closes may skip and still count as ONE visit. A real touch is a few bars
#: sitting against the line, not a single graze, so a visit has to be collapsed to one — and the
#: separation that makes the NEXT one a genuine return is the same "more than 5 bars apart" the level
#: suite already uses. Collapsing on adjacency alone counted one five-bar plateau as three touches,
#: which would let a line price never came back to certify itself as validated.
VISIT_GAP = 6


def touches(series: Series, d: Diagonal, lo: int, hi: int, margin: float = TOUCH_MARGIN) -> list[int]:
    """Bars in `[lo, hi)` whose CLOSE sits on the line — within `margin`, on either side of it.

    One index per VISIT (the first bar of it): two touches define a candidate line and the third
    validates it (m31-l1), and that count is only meaningful if price left the line in between.
    """
    line = projected(d, lo, hi)
    closes = np.asarray(series.close[lo:hi], dtype=float)
    near = np.flatnonzero(np.abs(_signed_excursion(closes, line, d.kind)) <= margin)
    out: list[int] = []
    last = -VISIT_GAP - 1
    for j in (lo + int(k) for k in near.tolist()):
        if j - last > VISIT_GAP:
            out.append(j)
        last = j
    return out


def worst_breach(series: Series, d: Diagonal, lo: int, hi: int) -> float:
    """The furthest a CLOSE gets beyond the line in `[lo, hi)`, as a fraction. <= 0 means never."""
    if hi <= lo:
        return 0.0
    line = projected(d, lo, hi)
    closes = np.asarray(series.close[lo:hi], dtype=float)
    return float(_signed_excursion(closes, line, d.kind).max())


def respected(
    series: Series, d: Diagonal, lo: int, hi: int, min_touches: int = 3, margin: float = BREACH_MARGIN
) -> bool:
    """The whole contract in one call: `min_touches` separated touches and no close through the line.

    This is the `zone_respected` equivalent m31 needed. What it deliberately does NOT check is the
    wicks — see the module docstring.
    """
    return len(touches(series, d, lo, hi)) >= min_touches and worst_breach(series, d, lo, hi) <= margin


def clamp_close_inside(
    close: np.ndarray, line: np.ndarray, kind: str, lo: int, hi: int, inset: float = 0.0005
) -> None:
    """Hold a close path on the inside of a sloped line over `[lo, hi)`, in place.

    `common.clamp_close_inside` for a moving line, and needed for the same reason: "never closed
    through it" has to be exactly true, not true in most seeds. Measured over 300 seeds, the ambient
    tail — a mean-reverting walk with a 1.1% stationary sd — wandered a BODY through a line the label
    said held once, which is a chart indistinguishable from the label next to it.

    A body is the close path, so no wick guard can reach it; it is bounded here, before the candles are
    derived. The `inset` is deliberately tiny: a designed visit that this pulls back sits ON the line
    rather than a hair through it, which is still a touch.
    """
    limit = line * (1.0 - inset) if kind == "resistance" else line * (1.0 + inset)
    span = slice(max(0, lo), min(hi, len(close)))
    if kind == "resistance":
        np.minimum(close[span], limit[span], out=close[span])
    else:
        np.maximum(close[span], limit[span], out=close[span])


def separation(a: Diagonal, b: Diagonal, index: int) -> float:
    """The gap between two lines at `index`, as a fraction of the lower one.

    A channel keeps this roughly constant; a wedge or a triangle shrinks it, which is the one claim
    `converging_lines` makes that has to be asserted rather than eyeballed.
    """
    pa, pb = price_at(a, index), price_at(b, index)
    return abs(pa - pb) / min(pa, pb)
