# SPDX-License-Identifier: AGPL-3.0-only
"""The pattern-injector contract for the generic `pattern_chart` generator.

An injector builds a full close path (warm-up + visible), declares the ground-truth label it planted,
and optionally exposes public overlays/levels (things the learner is meant to SEE and read, e.g.
moving averages or a Fibonacci grid) and a volume override (for volume-based patterns). Anything that
would reveal the answer — the label and the swing/zone annotations — is ground truth and is returned
separately so the generator can withhold it until grading.
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
    """A ground-truth overlay marker (a swing point / zone edge that reveals the answer). `index` is
    in FULL-series coords (warm-up included); the generator converts it to visible coords."""

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
class LevelGuard:
    """A drawn `Level`'s contract with the CANDLES, enforced in one shared place for exercises and
    figures alike (`apply_level_guards`).

    A level's price is planted by the injector, but the candles around it are not: `build_series`
    derives each bar's wick from a half-normal draw, so whether a bar actually touches the line — or
    randomly pokes through it — is luck. That is what made drawn levels look wrong: a resistance the
    range never once tested reads as an arbitrary line, and a `no_break` whose wick pierces the level
    contradicts its own label. A guard states what the label already claims, so the candles cannot
    disagree with the line:

    * `tests` — bars that must REACH the level. Their wick is extended to it (bodies untouched), so
      the line is one the market visibly respected rather than a number in empty space.
    * `no_breach` — `[lo, hi)` bar spans that must not trade beyond the level *at all*, wick
      included. Breaching wicks are clamped back to it. Spans where the pattern is meant to break
      through (a fakeout's poke, a Wyckoff spring, an engulfing overrun) are simply left out.

    Indices are FULL-series coords (warm-up included), like `Annotation.index`. Guards only ever move
    wicks: a body on the wrong side of the line is a shape bug the statistical level tests must catch,
    never something to paper over here.
    """

    price: float
    kind: str  # "support" | "resistance" — which side counts as "beyond"
    tests: tuple[int, ...] = ()
    no_breach: tuple[tuple[int, int], ...] = ()


@dataclass
class PatternResult:
    """What an injector returns. `close_full` is warm-up + visible; `overlays`/`volume_full` span the
    full series (the generator trims warm-up in lockstep with the candles); `levels` are price-space.
    `label`/`annotations` are ground truth and are never placed in the pre-answer payload."""

    close_full: Floats
    warmup: int
    label: str
    annotations: list[Annotation] = field(default_factory=list)
    overlays: dict[str, list[float]] = field(default_factory=dict)
    levels: list[Level] = field(default_factory=list)
    #: candle-space contracts for the `levels` above, applied by the generator (exercise) and the
    #: figure builder alike via `apply_level_guards`. See `LevelGuard`.
    level_guards: list[LevelGuard] = field(default_factory=list)
    volume_full: Floats | None = None
    #: optional secondary series shown in the oscillator pane (e.g. open interest for m17). Full
    #: length; the generator trims the warm-up like the candles. Used when ``indicator == "oi"``.
    oi_full: Floats | None = None
    #: optional cumulative-volume-delta series for the oscillator pane (m26). Full length, trimmed
    #: like the candles, and — unlike every other pane series — LINEAR: a CVD is a running sum of
    #: signed flow anchored at 0 when the visible window opens, so it legitimately sits at or below
    #: zero. Anything continuing it must work in linear space (see ``append_linear_continuation``).
    #: Used when ``indicator == "cvd"``.
    cvd_full: Floats | None = None
    #: optional full-length OHLC override. When an injector needs to shape individual candles that
    #: ``build_series`` derives stochastically — a rejection wick, a tweezers low, a clean engulfing
    #: body (m08 candle reactions) — it builds the Series itself and returns it here; the generator
    #: uses it verbatim instead of calling ``build_series``. Its ``close`` must match ``close_full``
    #: so indicators stay consistent. Left None by every other injector (build_series path unchanged).
    candles_full: Series | None = None
    #: figure-only hint for the resolution continuation's direction (+1 up / -1 down / 0 sideways).
    #: A candle reaction's payload is what follows it (a bounce off support, a drop off resistance,
    #: nothing after a doji); the injector knows the planted form, so it names the direction here for
    #: ``build_figure``. Never read in exercise mode; not part of the graded payload (golden unaffected).
    resolution_hint: float | None = None


class PatternInjector(ABC):
    #: registry key used by the exercise config
    name: ClassVar[str]
    #: every label this injector can plant (the config's targets/choices must be a subset)
    labels: ClassVar[tuple[str, ...]]
    #: True  -> a detection/prediction pattern whose resolution must stay off screen; the statistical
    #:          anti-leak test (last-N candles must not predict the label) is BLOCKING for it.
    #: False -> a classification pattern whose label IS the visible state (trend regime, oscillator
    #:          reading); it instead ships the credibility test (no synthetic spike; ambient tail).
    hides_resolution: ClassVar[bool] = True
    #: oscillator pane to render: "rsi" | "macd" | "none"
    indicator: ClassVar[str] = "rsi"

    @abstractmethod
    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        """Build the scenario for `target` (one of `labels`). Deterministic given `rng`."""
