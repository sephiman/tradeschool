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
    volume_full: Floats | None = None
    #: optional secondary series shown in the oscillator pane (e.g. open interest for m17). Full
    #: length; the generator trims the warm-up like the candles. Used when ``indicator == "oi"``.
    oi_full: Floats | None = None


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
