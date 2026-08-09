# SPDX-License-Identifier: AGPL-3.0-only
"""Trendline / channel injector (m31-l1): the horizontal level's moving twin.

Five labels in two families over one geometry — three about a single diagonal (`line_holds`,
`line_break`, `line_fakeout`, the m08 fakeout trio with the level in motion) and two about the channel
its parallel makes (`channel_intact`, `channel_broken`).

BIDIRECTIONAL FROM BIRTH. The bull-only rule the m30 injectors carry (`test_chart_bands.py`, §3b) is a
consequence of their prompts describing the bullish geometry in words, and this family's prompts are
written symmetric instead — "the line", "beyond it", never "the high". So `rng` picks rising or falling
per seed and both must render and pass every contract; `test_chart_diagonals.py` sweeps for both.

The whole path is built in LINEAR price around the line, not in log space like every other injector
here, and that is not a style choice: a diagonal renders as a straight segment on a linear price scale,
so a constant LOG slope would draw a curve the line misses by percents — several times the margin the
respect contract is measured with.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    Diagonal,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    candle_extreme,
    shape_from_points,
    with_warmup,
)
from tradeschool.exercises.charts.patterns.diagonals import clamp_close_inside as clamp_inside

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_BASE_VOLUME = 1000.0

# Where the line is anchored, where price comes back to it, and where it runs to the far edge between
# those visits. Four designed touches: two define the candidate line, the third validates it (m31-l1),
# and the fourth is the margin that keeps a seed whose noise eats one touch from failing the contract.
_TOUCH_F = (0.06, 0.30, 0.54, 0.72)
_PUSH_F = (0.18, 0.42, 0.63)
_DECIDE = 0.80  # where the label happens
_RECLAIM = 0.86  # where a `line_fakeout` is back inside the line for good
_HOLD = 0.88  # ...and where price settles afterwards, before the ambient tail
_PRE_DECIDE = 0.77  # the last bar of the rhythm; the contract is measured up to here

# The channel's width, as a fraction of the base price, and the total advance of the line across the
# window. Both are draws, so no two seeds print the same slope.
_WIDTH = (0.055, 0.075)
_ADVANCE = (0.16, 0.26)

# Everything below is in OSC units: 0 sits ON the anchor line, 1 on its parallel. Expressing the design
# this way is what makes the respect contract checkable — the distance from the line is a parameter
# rather than an outcome.
_TOUCH_OSC = 0.035  # ~0.23% off the line at a designed touch: inside `diagonals.TOUCH_MARGIN`...
_NOISE = 0.003  # ...with room for the texture's peak before it reaches `BREACH_MARGIN`
_PUSH_OSC = 0.96  # how close a push gets to the opposite edge — a touch of it, for the channel labels
#: Half-width of a visit, in window fractions. Every visit is a PLATEAU, never a vertex: `shape_from_
#: points` smooths over three bars, and a single-bar V gets its point lifted to twice the designed
#: distance — measured over 600 seeds, that left 143 of them with ONE countable touch instead of four,
#: i.e. a line the contract could not call validated. A plateau is also what a real touch looks like.
_PLATEAU = 0.018
#: How far from the decided line every label settles — the SAME distance for all five, so the answer is
#: never readable off a ruler (`test_chart_diagonals.py` asserts it, as m08's fakeout does for its
#: level). 4.5% of price, which is five sigma of the ambient tail's walk: the tail cannot wander back
#: across the line and print the very break a `holds` label denies.
_HOLD_D = 0.045
#: The poke a `line_fakeout` makes before reclaiming, and the close a `line_break` settles at, in osc
#: units. Both are real BODY closes beyond the line — a wick through a diagonal is not a break at all
#: (m31-l1), so a label that turned on one would teach the opposite of the lesson.
_POKE_OSC = -0.17
_BREAK_OSC = -0.20
#: Volume window carrying the participation tell, as window fractions, and the multipliers. Same shape
#: as m14: a genuine break brings the crowd, a fakeout does not.
_VOL_LO, _VOL_HI = 0.78, 0.86
_VOL_SURGE = (2.8, 3.9)
_VOL_THIN = (0.5, 0.8)

_SINGLE = ("line_holds", "line_break", "line_fakeout")
#: The channel family. Two ways a channel ENDS, and they are not the same event: `channel_broken`
#: leaves through the parallel — an acceleration, in the direction the channel was already going —
#: and `channel_failed` leaves through the anchor line the rhythm was built on, which is the rhythm
#: itself giving out. Nothing privileges either, and a generator that could only plant one would
#: teach that it did: see the note on `_resolution_hint`.
_CHANNEL = ("channel_intact", "channel_broken", "channel_failed")


def _visit(f: float, osc: float) -> list[tuple[float, float]]:
    """A visit to one edge: price sits against it for a few bars, then leaves. See `_PLATEAU`."""
    return [(f - _PLATEAU, osc), (f + _PLATEAU, osc)]


def _osc_points(target: str, hold_osc: float) -> list[tuple[float, float]]:
    """The rhythm, then the decision — in osc units, identical for every label until `_PRE_DECIDE`."""
    rhythm: list[tuple[float, float]] = []
    for i, f in enumerate(_TOUCH_F):
        rhythm += _visit(f, _TOUCH_OSC)
        if i < len(_PUSH_F):
            rhythm += _visit(_PUSH_F[i], _PUSH_OSC)
    rhythm.sort()
    pre = [*rhythm, (_PRE_DECIDE, 0.35)]

    if target == "line_holds":  # comes back to the line, is rejected, holds well inside
        return [*pre, *_visit(_DECIDE, _TOUCH_OSC), (_HOLD, hold_osc), (1.00, hold_osc)]
    if target == "line_break":  # closes clean through and holds through
        return [*pre, *_visit(_DECIDE, _BREAK_OSC), (_HOLD, -hold_osc), (1.00, -hold_osc)]
    if target == "line_fakeout":  # closes through, then reclaims and holds inside
        return [*pre, *_visit(_DECIDE, _POKE_OSC), (_HOLD, hold_osc), (1.00, hold_osc)]
    # The channel labels decide at the PARALLEL (osc 1), so their hold is measured from there.
    if target == "channel_intact":
        return [
            *pre, *_visit(_DECIDE, 1.0 - _TOUCH_OSC),
            (_HOLD, 1.0 - hold_osc), (1.00, 1.0 - hold_osc),
        ]
    if target == "channel_broken":  # accelerates out through the far edge
        return [*pre, *_visit(_DECIDE, 1.20), (_HOLD, 1.0 + hold_osc), (1.00, 1.0 + hold_osc)]
    if target == "channel_failed":  # ...or gives out through the line it was built on
        return [*pre, *_visit(_DECIDE, _BREAK_OSC), (_HOLD, -hold_osc), (1.00, -hold_osc)]
    raise ValueError(f"unknown trend_channel label {target!r}")  # pragma: no cover - config-validated


class TrendChannelInjector(PatternInjector):
    name: ClassVar[str] = "trend_channel"
    labels: ClassVar[tuple[str, ...]] = (*_SINGLE, *_CHANNEL)
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in self.labels:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown trend_channel label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        rising = bool(rng.integers(0, 2))
        sign = 1.0 if rising else -1.0
        width = base * float(rng.uniform(*_WIDTH))
        advance = base * float(rng.uniform(*_ADVANCE))

        # The anchor line, in price. `sign` mirrors the entire construction: a rising trend hangs its
        # support underneath and price rides above it; a falling one hangs its resistance overhead and
        # price rides below. Both read as the same question.
        i0 = int(_TOUCH_F[0] * n)
        slope = sign * advance / n
        x = np.arange(n, dtype=float)
        line = base + slope * (x - i0)

        hold_osc = _HOLD_D * base / width
        osc = shape_from_points(_osc_points(target, hold_osc), n)
        close_visible = (line + sign * osc * width) * np.exp(bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)

        # What each label claims about the line, made exactly true rather than true in most seeds. The
        # designed path already sits where it should; what these bound is the NOISE and the ambient
        # tail, whose random walk put a body through a `line_holds` line once in 300 seeds.
        kind = "support" if rising else "resistance"
        opposite = "resistance" if rising else "support"
        parallel = line + sign * width
        decide_bar = int(_DECIDE * n)
        hold_bar = int(_RECLAIM * n)
        # The rhythm is what the drawn line is evidence OF, so no label may breach it before deciding.
        clamp_inside(close_visible, line, kind, 0, decide_bar)
        if target in ("line_holds", "channel_intact", "channel_broken"):
            clamp_inside(close_visible, line, kind, 0, n)  # the anchor line is never given up
        if target == "line_fakeout":
            clamp_inside(close_visible, line, kind, hold_bar, n)  # ...reclaimed, and held from there
        if target in ("channel_intact", "channel_failed"):
            # `channel_failed` leaves through the ANCHOR, so its far edge has to hold all the way —
            # otherwise the chart shows a channel that lost both lines and names only one of them.
            clamp_inside(close_visible, parallel, opposite, 0, n)
        elif target == "channel_broken":
            clamp_inside(close_visible, parallel, opposite, 0, decide_bar)

        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        # Drawn from the first designed touch to the right edge — which is where a trader would draw it,
        # and what makes the projection past the rhythm the thing the decision is judged against.
        drawn = Diagonal(
            start=WARMUP + i0,
            end=WARMUP + n - 1,
            start_price=round(float(line[i0]), 2),
            end_price=round(float(line[n - 1]), 2),
            label="channel" if target in _CHANNEL else "trendline",
            kind=kind,
        )
        diagonals = [drawn]
        if target in _CHANNEL:
            diagonals.append(
                Diagonal(
                    start=drawn.start,
                    end=drawn.end,
                    start_price=round(float(line[i0] + sign * width), 2),
                    end_price=round(float(line[n - 1] + sign * width), 2),
                    label="channel_parallel",
                    # The far edge is the opposite kind: price is INSIDE when it sits below a rising
                    # channel's top, so that line is the resistance the channel labels decide at.
                    kind="resistance" if rising else "support",
                )
            )

        volume = _BASE_VOLUME * (0.75 + 0.5 * np.abs(rng.normal(0.0, 1.0, WARMUP + n)))
        v0, v1 = WARMUP + int(_VOL_LO * n), WARMUP + int(_VOL_HI * n)
        if target in ("line_break", "channel_broken", "channel_failed"):
            volume[v0:v1] *= rng.uniform(*_VOL_SURGE)  # the crowd came with it
        elif target == "line_fakeout":
            volume[v0:v1] *= rng.uniform(*_VOL_THIN)  # ...and here it did not

        # The rhythm's visits, marked on the CANDLES rather than on the close path: a reader reads a
        # touch off the wick that reached the line, and `candle_extreme` is what finds that bar.
        pivot = "low" if rising else "high"
        half = max(2, int(0.03 * n))
        touches = [
            Annotation(
                index=candle_extreme(series, WARMUP + int(f * n) - half, WARMUP + int(f * n) + half, pivot),
                kind=pivot,
                label="touch",
            )
            for f in _TOUCH_F
        ]
        decide = candle_extreme(
            series,
            WARMUP + int(_DECIDE * n) - half,
            WARMUP + int(_DECIDE * n) + half,
            # The decision is read off the edge it happens at: the far edge for the two labels that
            # end at the parallel, the anchor for everything that ends at the line itself.
            ("high" if rising else "low")
            if target in ("channel_intact", "channel_broken")
            else pivot,
        )
        # One bar may carry only one marker (`test_chart_annotations.py`), and two neighbouring visits
        # can resolve to the same candle. The decision wins, then the earliest touch.
        by_bar: dict[int, Annotation] = {}
        for a in (*touches, Annotation(index=decide, kind="marker", label="test")):
            by_bar.setdefault(a.index, a)
        by_bar[decide] = Annotation(index=decide, kind="marker", label="test")
        annotations = [by_bar[i] for i in sorted(by_bar)]

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            diagonals=diagonals,
            volume_full=volume,
            # A break runs on; a hold or a reclaim resumes the trend the line was drawn under. Stated
            # here rather than left to a per-injector default because the direction depends on the
            # seed's own `sign`, which only the injector knows.
            resolution_hint=_resolution_hint(target, sign),
        )


def _resolution_hint(target: str, sign: float) -> float:
    """Which way the chart is already going when the injector hands it over.

    Note what the two channel endings do here, because it is the whole reason `channel_failed` exists:
    `channel_broken` continues WITH the slope and `channel_failed` runs against it. A figure that showed
    only the first would be teaching "channels break in their own direction" by example — which is not a
    rule this course endorses, and `fig-m31-channel` now draws one of each.
    """
    if target in ("line_break", "channel_failed"):
        return -sign  # through the line and away from the trend it supported
    if target == "channel_intact":
        return 0.0  # staying inside a channel is not a direction
    return sign  # holds, reclaims, and the channel exit that accelerates out of the far edge
