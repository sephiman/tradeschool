# SPDX-License-Identifier: AGPL-3.0-only
"""Swing-structure injector (m08-l1): the labelled staircase, and the swing that breaks it.

Plants m08-l1's prose ladder with its pivots MARKED, as log offsets so the shape is the lesson's while
the absolute prices come from the seed. A CLASSIFICATION injector, so no last-candle leak test.

Pivot markers are anchored to the rendered candles (`resolve_candle_pivot`), not the close path: a
label saying "this is the higher high" has to sit on the bar whose wick a learner would measure.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    TAIL,
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    candle_extreme,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# The ladder of m08-l1, and the fall that breaks it. Ratios, not prices: `_off` turns each into a log
# offset from the first low, so the staircase keeps the lesson's proportions at any base price.
_L0, _HH1, _HL1, _HH2, _HL2, _HH3 = 100.0, 110.0, 104.0, 118.0, 109.0, 126.0
_LOWER_LOW = 105.5  # below _HL2 — the first lower low, which is what makes it a CHoCH

# Half-width (in window fractions) of the flat planted at each pivot. A single control point is shaved
# by the 3-window smoothing, which moves the extreme off the bar the marker points at.
_PLATEAU = 0.016
# Peak candle texture. It must stay well inside the smallest designed separation (HL1 -> HL2 is 4.8%)
# so noise can never reorder two rungs of the ladder and contradict a marker.
_NOISE = 0.004

# The ladder: (window fraction, ratio, marker label). The opening low is deliberately unlabelled — it is
# the reference the first HL is higher THAN, not itself a higher low.
#
# Both labels share these fractions, and the CHoCH ladder is this one PLUS a failing swing. That is the
# comparison the figure is for: two charts that read identically until the last swing, where one makes
# another higher low and the other does not.
_UPTREND: tuple[tuple[float, float, str], ...] = (
    (0.06, _L0, ""),
    (0.20, _HH1, "HH"),
    (0.32, _HL1, "HL"),
    (0.46, _HH2, "HH"),
    (0.58, _HL2, "HL"),
    (0.72, _HH3, "HH"),
)
_CHOCH: tuple[tuple[float, float, str], ...] = (*_UPTREND, (0.88, _LOWER_LOW, "CHoCH"))
# Where each ladder goes after its last pivot: a shallow unresolved pullback that keeps the staircase
# intact (uptrend), or the fall through the last higher low and the bounce that completes it (choch).
# Single points — nothing here is marked, and each stays a wide margin clear of the marked pivots.
_UPTREND_AFTER: tuple[tuple[float, float], ...] = ((0.80, 118.0), (0.92, 120.0), (1.00, 120.5))
_CHOCH_AFTER: tuple[tuple[float, float], ...] = ((0.80, 111.0), (0.95, 108.5), (1.00, 108.5))


def _off(ratio: float) -> float:
    return float(np.log(ratio / _L0))


class MarketStructureInjector(PatternInjector):
    name: ClassVar[str] = "market_structure"
    labels: ClassVar[tuple[str, ...]] = ("uptrend_ladder", "choch_after_uptrend")
    hides_resolution: ClassVar[bool] = False  # the label IS the visible sequence of swings
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target == "uptrend_ladder":
            pivots, after, hint = _UPTREND, _UPTREND_AFTER, 1.0
        elif target == "choch_after_uptrend":
            pivots, after, hint = _CHOCH, _CHOCH_AFTER, -1.0
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown market_structure label {target!r}")

        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        pts: list[tuple[float, float]] = []
        for frac, ratio, _label in pivots:
            pts += [(frac - _PLATEAU, _off(ratio)), (frac + _PLATEAU, _off(ratio))]
        pts += [(frac, _off(ratio)) for frac, ratio in after]
        pts.sort()

        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)
        # The candles are built HERE (and shipped as `candles_full`) so the pivot markers can be
        # anchored to the wicks the learner reads rather than to the close path they were designed in.
        series = build_series(rng, close_full)

        fracs = [f for f, _r, _l in pivots]

        def swing_window(i: int, frac: float) -> tuple[int, int]:
            """The segment a pivot OWNS: midpoint before it to midpoint after it.

            The LAST pivot's segment stops where the AMBIENT TAIL begins — without that bound a tail
            wick below the CHoCH low would drag the CHoCH label onto a noise candle.
            """
            lo = ((fracs[i - 1] + frac) / 2) if i > 0 else 0.0
            if i + 1 == len(fracs):
                return WARMUP + int(lo * n), WARMUP + n - TAIL
            return WARMUP + int(lo * n), WARMUP + int(((frac + fracs[i + 1]) / 2) * n) + 1

        annotations: list[Annotation] = []
        for i, (frac, _ratio, label) in enumerate(pivots):
            if not label:
                continue
            kind = "high" if label == "HH" else "low"  # HL and CHoCH are both lows
            lo, hi = swing_window(i, frac)
            annotations.append(
                Annotation(index=candle_extreme(series, lo, hi, kind), kind=kind, label=label)
            )

        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            candles_full=series,
            resolution_hint=hint,
        )
