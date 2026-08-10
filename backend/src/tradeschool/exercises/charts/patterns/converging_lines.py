# SPDX-License-Identifier: AGPL-3.0-only
"""Wedge / triangle injector (m15-l2): compression between two lines that are closing on each other.

Two label families over one geometry, because they are two readings of the same chart and an exercise
picks whichever it asks about:

* SHAPE — `rising_wedge`, `falling_wedge`, `symmetric_triangle`, `ascending_triangle`,
  `descending_triangle`, and `parallel_channel` as the negative control (the m34 injectors' `no_zone` /
  `no_imbalance` role: the chart that looks like the family and is not a member of it, without which
  "converging" is a word no answer can be wrong about).
* RESOLUTION — `break_confirmed`, `break_unconfirmed`, `compression_holding`: the same convergence,
  carried to the point where it either resolves under m08's + m14's discipline (a BODY beyond the line
  with participation behind it) or does not.

Bidirectional by construction — every shape names its own direction and the resolution family draws one
at random, so there is no direction to guard. Like `trend_channel` the whole path is built in LINEAR
price around the two lines; see that module for why.
"""

from __future__ import annotations

from collections.abc import Callable
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

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_BASE_VOLUME = 1000.0

#: The opening width of the shape, and how much of it survives to the right edge.
#:
#: The width looks large for a coil, and it is load-bearing at exactly that size. "Each bar's range
#: narrows" (m15-l2) is a claim about the CANDLES, and `build_series` floors the volatility it draws
#: wicks from at 0.4% — so once a swing moves less than that per bar, the bars stop shrinking with the
#: shape. At (0.085, 0.115) the late swings travelled 0.22%/bar, under the floor, and measured over 80
#: seeds the closing bars were 1.03x the opening ones: a coil whose lines converged and whose candles
#: did not, which is the lesson's central claim quietly not being true of its own figure. At this width
#: the last swings move ~0.6%/bar, clear of the floor, and the bars narrow with the lines.
_WIDTH = (0.24, 0.30)
_CONVERGENCE = 0.26
#: Net drift of the shape's midline across the window, as a fraction of base — the "price drifts" half
#: of the definition. Each shape below supplies its own sign.
_DRIFT = (0.06, 0.10)

_DECIDE = 0.82  # where the resolution family resolves
_HOLD = 0.90
_PRE_DECIDE = 0.79
#: The swings, as window fractions. EIGHT visits alternating between the lines, so each is touched four
#: times: three is the minimum that validates a line (m15-l1) and leaving no margin above it means one
#: seed whose noise lifts a visit off the line prints a coil the contract has to reject.
_SWING_F = (0.07, 0.17, 0.27, 0.37, 0.47, 0.57, 0.66, 0.74)
_PLATEAU = 0.016  # half-width of a visit — a vertex would be smoothed away (see `trend_channel`)
#: How close a visit gets to its line, as a fraction of PRICE — not of the current width, which is the
#: whole difficulty here. The span shrinks by a factor of four across the window, so one osc value means
#: a visit 0.9% off the line at the open and 0.3% off it at the close: the early ones stop counting as
#: touches at all, and measured over 120 seeds that left the upper line of every shape with two.
_EDGE_D = 0.0022
_NOISE = 0.0028

_HOLD_D = 0.045  # the settle distance from the decided line, identical for every resolution label
_POKE_OSC = -0.18  # a body close beyond the line, in units of the width at that bar
_BREAK_OSC = -0.30
_VOL_LO, _VOL_HI = 0.80, 0.88
_VOL_SURGE = (2.8, 3.9)
_VOL_THIN = (0.5, 0.8)

#: Every shape as (how much of the convergence the CEILING contributes, the midline's own slope in
#: units of the same convergence rate `k`, does it converge at all). Writing them this way is what makes
#: the family one geometry rather than six: the span is always `w0 - k*x`, so what tells the shapes
#: apart is only how that shrink is split between the two lines and where the middle is going.
#:
#:   upper slope = (mid_k - ceiling_share) * k      lower slope = (mid_k + 1 - ceiling_share) * k
#:
#: which is why a flat ceiling is `mid_k = +0.5` and a flat floor is `mid_k = -0.5`, and why a wedge is
#: just a triangle whose midline outruns its own convergence.
_SHAPES: dict[str, tuple[float, float, bool]] = {
    "rising_wedge": (0.5, 1.6, True),  # both lines up, the floor steeper: buyers give more than sellers
    "falling_wedge": (0.5, -1.6, True),  # both down, the ceiling steeper
    "symmetric_triangle": (0.5, 0.0, True),  # they meet in the middle
    "ascending_triangle": (0.5, 0.5, True),  # a flat ceiling, a rising floor
    "descending_triangle": (0.5, -0.5, True),  # a falling ceiling, a flat floor
    "parallel_channel": (0.5, 1.6, False),  # the control: same drift, the two lines never approach
}
_SHAPE_LABELS = tuple(_SHAPES)
_RESOLUTION_LABELS = ("break_confirmed", "break_unconfirmed", "compression_holding")
#: What the resolution family draws its geometry from — every converging shape, never the control.
_CONVERGING = tuple(s for s in _SHAPES if s != "parallel_channel")


def _visit(f: float, osc: float) -> list[tuple[float, float]]:
    return [(f - _PLATEAU, osc), (f + _PLATEAU, osc)]


def _osc_points(
    target: str, hold_osc: float, edge: Callable[[float], float]
) -> list[tuple[float, float]]:
    """Where price sits BETWEEN the lines: 0 on the lower one, 1 on the upper. Same coil for all."""
    coil: list[tuple[float, float]] = []
    for i, f in enumerate(_SWING_F):
        coil += _visit(f, (1.0 - edge(f)) if i % 2 == 0 else edge(f))
    pre = [*coil, (_PRE_DECIDE, 0.5)]
    if target not in _RESOLUTION_LABELS:
        # A shape question is about the coil, so it never resolves: the last stretch keeps coiling.
        return [*pre, *_visit(0.86, 1.0 - edge(0.86)), (1.00, 0.5)]
    if target == "compression_holding":
        return [*pre, *_visit(_DECIDE, edge(_DECIDE)), (_HOLD, 0.5), (1.00, 0.5)]
    if target == "break_confirmed":
        return [*pre, *_visit(_DECIDE, _BREAK_OSC), (_HOLD, -hold_osc), (1.00, -hold_osc)]
    return [*pre, *_visit(_DECIDE, _POKE_OSC), (_HOLD, hold_osc), (1.00, hold_osc)]


class ConvergingLinesInjector(PatternInjector):
    name: ClassVar[str] = "converging_lines"
    labels: ClassVar[tuple[str, ...]] = (*_SHAPE_LABELS, *_RESOLUTION_LABELS)
    #: The label IS the visible state — which shape is drawn, or what the price action already did to
    #: it — so the anti-leak test does not apply and the credibility test is the gate (see `base`).
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in self.labels:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown converging_lines label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        shape = target if target in _SHAPES else str(rng.choice(_CONVERGING))
        ceiling_share, mid_k, converges = _SHAPES[shape]
        if not converges:
            mid_k *= float(rng.choice((-1.0, 1.0)))  # the control drifts either way, like everything else

        width0 = base * float(rng.uniform(*_WIDTH))
        # One rate does both jobs: it is how much of the opening width the two lines eat between them
        # per bar, AND the unit the midline's own slope is expressed in. The span therefore runs from
        # `width0` to `_CONVERGENCE * width0` across the window for every shape that converges — and
        # the control simply does not spend it, which is the only thing that makes it the control.
        rate = width0 * (1.0 - _CONVERGENCE) / n
        k = rate if converges else 0.0
        x = np.arange(n, dtype=float)
        mid = base + mid_k * rate * x
        upper = mid + width0 / 2.0 - ceiling_share * k * x
        lower = mid - width0 / 2.0 + (1.0 - ceiling_share) * k * x
        span = upper - lower

        # The settle distance is measured where price settles, so the osc it corresponds to is read off
        # the span AT that bar — the coil is narrower there than it was at the open, and using the mean
        # would leave every resolution label holding well inside the ambient tail's reach.
        hold_osc = _HOLD_D * base / float(span[int(_HOLD * n)])
        osc = shape_from_points(
            _osc_points(
                target, hold_osc, lambda f: _EDGE_D * base / float(span[min(int(f * n), n - 1)])
            ),
            n,
        )
        close_visible = (lower + osc * span) * np.exp(bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        # Each line is anchored at ITS OWN first visit, not at a shared bar: the swings alternate, so
        # the lower line's first touch is one swing later. Anchoring both at the earlier one drew the
        # floor 2% below anything price had done, which is a line the chart cannot corroborate.
        i1 = n - 1
        iu, il = int(_SWING_F[0] * n), int(_SWING_F[1] * n)
        diagonals = [
            Diagonal(
                start=WARMUP + iu, end=WARMUP + i1,
                start_price=round(float(upper[iu]), 2), end_price=round(float(upper[i1]), 2),
                label="upper", kind="resistance",
            ),
            Diagonal(
                start=WARMUP + il, end=WARMUP + i1,
                start_price=round(float(lower[il]), 2), end_price=round(float(lower[i1]), 2),
                label="lower", kind="support",
            ),
        ]

        volume = _BASE_VOLUME * (0.75 + 0.5 * np.abs(rng.normal(0.0, 1.0, WARMUP + n)))
        # Compression is quiet by definition, so the coil's volume fades into the decision — the half of
        # "compression -> expansion" that a volume pane can show at all.
        fade = np.linspace(1.0, 0.55, n)
        volume[WARMUP:] *= fade
        v0, v1 = WARMUP + int(_VOL_LO * n), WARMUP + int(_VOL_HI * n)
        if target == "break_confirmed":
            volume[v0:v1] *= rng.uniform(*_VOL_SURGE)
        elif target == "break_unconfirmed":
            volume[v0:v1] *= rng.uniform(*_VOL_THIN)

        half = max(2, int(0.025 * n))
        annotations: list[Annotation] = []
        for i, f in enumerate(_SWING_F):
            kind = "high" if i % 2 == 0 else "low"
            annotations.append(
                Annotation(
                    index=candle_extreme(
                        series, WARMUP + int(f * n) - half, WARMUP + int(f * n) + half, kind
                    ),
                    kind=kind,
                    label="touch",
                )
            )
        if target in _RESOLUTION_LABELS:
            annotations.append(
                Annotation(
                    index=candle_extreme(
                        series, WARMUP + int(_DECIDE * n) - half, WARMUP + int(_DECIDE * n) + half, "low"
                    ),
                    kind="marker",
                    label="test",
                )
            )
        by_bar: dict[int, Annotation] = {}
        for a in annotations:
            by_bar.setdefault(a.index, a)
        annotations = [by_bar[i] for i in sorted(by_bar)]

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            diagonals=diagonals,
            volume_full=volume,
            # Compression resolves into expansion; which WAY is the part m15-l2 refuses to promise, so
            # the hint states only what the chart already shows — a confirmed break runs on, a rejected
            # one goes back the other way, a coil still coiling goes nowhere.
            resolution_hint=(
                -1.0 if target == "break_confirmed" else 1.0 if target == "break_unconfirmed" else 0.0
            ),
        )
