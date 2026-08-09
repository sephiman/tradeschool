# SPDX-License-Identifier: AGPL-3.0-only
"""The pattern-injector contract for the generic `pattern_chart` generator.

Anything revealing the answer (label, annotations, bands) is returned separately from the public
overlays/levels, so the generator can withhold it until grading.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import ClassVar

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.types import Series

Floats = NDArray[np.float64]


@dataclass
class Annotation:
    """A ground-truth marker. `index` is FULL-series coords; the generator converts to visible."""

    index: int
    kind: str  # "high" | "low" | "marker"
    label: str = ""


@dataclass
class Level:
    """A horizontal price line the learner SEES (support/resistance, a Fibonacci level). Public."""

    price: float
    label: str = ""
    kind: str = "level"  # "support" | "resistance" | "fib" | "level"


@dataclass
class Band:
    """A shaded price ZONE (m30's origin zone / imbalance), which a horizontal `Level` cannot express.

    GROUND TRUTH, withheld like `annotations`: drawing the zone on an exercise chart *is* the answer.
    Its contract with the candles is ASSERTED by `tests/test_chart_bands.py`, never enforced by
    mutation — widening a wick to "test" an imbalance would destroy the untraded span that IS its
    claim. Where a bound is genuinely needed, the injector ships an *undrawn* `LevelGuard` instead.
    """

    low: float
    high: float
    label: str = ""
    kind: str = "origin"  # "origin" | "imbalance"


@dataclass
class Diagonal:
    """A SLOPED line the learner SEES: a trendline, a channel edge, a wedge boundary (m31). Public.

    Two anchors in FULL-series coords, and the price at each. The renderer draws the straight segment
    between them; `diagonals.price_at` projects it anywhere, including past `end`. LINEAR in price,
    because that is what a straight line on a linear price scale is.

    Unlike a `Level`, a diagonal has NO `LevelGuard` equivalent and never moves a candle. A horizontal
    level is a price the book remembers, so a wick through it is a defect worth repairing; a diagonal is
    a rate of advance nobody is obliged to maintain, so a wick through it is the ordinary case m31-l1
    teaches you to ignore. Its contract is therefore ASSERTED on the CLOSES, in
    `tests/test_chart_diagonals.py` — see `diagonals.respect`.
    """

    start: int
    end: int
    start_price: float
    end_price: float
    label: str = ""
    kind: str = "support"  # "support" | "resistance" — which side of the line is INSIDE the shape


@dataclass
class LevelGuard:
    """A drawn `Level`'s contract with the CANDLES, applied by `apply_level_guards`.

    `tests` bars must reach the level (wick extended to it); `no_breach` `[lo, hi)` spans must not
    trade beyond it at all. Indices are FULL-series coords. Guards only ever move wicks — a body on
    the wrong side is a shape bug for the level tests to catch, not something to paper over.
    """

    price: float
    kind: str  # "support" | "resistance" — which side counts as "beyond"
    tests: tuple[int, ...] = ()
    no_breach: tuple[tuple[int, int], ...] = ()


@dataclass
class PatternResult:
    """What an injector returns. Everything `_full` spans warm-up + visible; the generator trims it."""

    close_full: Floats
    warmup: int
    label: str
    annotations: list[Annotation] = field(default_factory=list)
    overlays: dict[str, list[float]] = field(default_factory=dict)
    levels: list[Level] = field(default_factory=list)
    #: sloped lines the learner sees (m31). Public like `levels` — a trendline the question is about
    #: has to be on the chart, or there is nothing to judge a break against.
    diagonals: list[Diagonal] = field(default_factory=list)
    #: shaded price zones (m30). GROUND TRUTH like `annotations` — see `Band`.
    bands: list[Band] = field(default_factory=list)
    #: candle-space contracts for the `levels` above — see `LevelGuard`.
    level_guards: list[LevelGuard] = field(default_factory=list)
    volume_full: Floats | None = None
    #: open interest for the oscillator pane (m17). Used when ``indicator == "oi"``.
    oi_full: Floats | None = None
    #: cumulative volume delta for the oscillator pane (m26). Used when ``indicator == "cvd"``.
    #: LINEAR, unlike every other pane series, and legitimately negative — continue it with
    #: ``append_linear_continuation``, never the log-space version.
    cvd_full: Floats | None = None
    #: signed series for the ZERO-CENTRED oscillator pane. Used when ``indicator == "momentum"``.
    #: A generic pane, not m32's indicator: any injector may hand it a series read against zero and get
    #: a histogram coloured by sign. Linear, like ``cvd_full`` and for the same reason.
    momentum_full: Floats | None = None
    #: optional per-bar STATE row for that pane, 1.0 where the state is on (m32: Bollinger inside
    #: Keltner). Drawn as dots along the zero line, never as a second histogram — it is a flag, not a
    #: quantity. Ignored unless ``momentum_full`` is present.
    momentum_state_full: Floats | None = None
    #: OHLC override for injectors shaping individual candles (m08). Used verbatim instead of
    #: ``build_series``; its ``close`` must match ``close_full`` so indicators stay consistent.
    candles_full: Series | None = None
    #: figure-only direction for the resolution continuation (+1 up / -1 down / 0 sideways).
    resolution_hint: float | None = None


class PatternInjector(ABC):
    #: registry key used by the exercise config
    name: ClassVar[str]
    #: every label this injector can plant (the config's targets/choices must be a subset)
    labels: ClassVar[tuple[str, ...]]
    #: True  -> resolution must stay off screen; the statistical anti-leak test is BLOCKING.
    #: False -> the label IS the visible state; ships the credibility test instead.
    hides_resolution: ClassVar[bool] = True
    #: oscillator pane to render: "rsi" | "macd" | "momentum" | "none"
    indicator: ClassVar[str] = "rsi"

    @abstractmethod
    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        """Build the scenario for `target` (one of `labels`). Deterministic given `rng`."""
