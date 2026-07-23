# SPDX-License-Identifier: AGPL-3.0-only
"""Derivatives-data injector (module m17): open interest read against price.

Price rises the SAME way for every label — so price can never betray the answer — and the tell is
what OPEN INTEREST (shown in the lower pane) does underneath that rally:

* ``rising_oi`` — OI climbs with price: new money is entering, the move is backed (healthy trend).
* ``falling_oi`` — OI falls while price rises: the rally is shorts covering, not fresh buying — no
  conviction, prone to stall.
* ``flat_oi`` — OI barely moves: thin participation, a low-conviction drift.

Since the price path is identical across labels, the last-candle price distribution is identical
(the anti-leak test passes trivially) and the resolution — whether the rally holds — is off screen.
The learner must read the OI line, not the candles. (Funding and liquidation clusters are taught in
m17's lesson and quizzes; this injector isolates the OI-vs-price reading.)
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.patterns.base import PatternInjector, PatternResult
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_BASE_OI = 10000.0


class DerivativesInjector(PatternInjector):
    name: ClassVar[str] = "derivatives"
    labels: ClassVar[tuple[str, ...]] = ("rising_oi", "falling_oi", "flat_oi")
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "oi"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        # Price: a mild rally, built IDENTICALLY for every label (draws happen before the OI branch),
        # so price carries no information about the label.
        g = float(rng.uniform(0.14, 0.22))
        price_pts = [
            (0.00, 0.00), (0.16, 0.22 * g), (0.28, 0.15 * g), (0.44, 0.48 * g), (0.58, 0.42 * g),
            (0.74, 0.78 * g), (0.86, 0.72 * g), (1.00, g),
        ]
        close_visible = base * np.exp(shape_from_points(price_pts, n) + bounded_noise(rng, n, amp=0.014))
        apply_ambient_tail(rng, close_visible)
        close_full = with_warmup(rng, close_visible)

        # OI: rises / falls / stays flat under that same rally.
        if target == "rising_oi":
            oi_pts = [(0.0, 0.0), (0.3, 0.09), (0.5, 0.07), (0.7, 0.18), (1.0, 0.26)]
        elif target == "falling_oi":
            oi_pts = [(0.0, 0.0), (0.3, -0.08), (0.5, -0.06), (0.7, -0.17), (1.0, -0.26)]
        elif target == "flat_oi":
            oi_pts = [(0.0, 0.0), (0.25, 0.02), (0.5, -0.02), (0.75, 0.02), (1.0, 0.0)]
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown derivatives label {target!r}")
        oi_visible = _BASE_OI * np.exp(shape_from_points(oi_pts, n) + bounded_noise(rng, n, amp=0.012))
        # Prepend a flat warm-up for OI so it aligns with the (dropped) price warm-up.
        oi_full = np.concatenate([np.full(WARMUP, oi_visible[0]), oi_visible])

        return PatternResult(
            close_full=close_full, warmup=WARMUP, label=target, oi_full=oi_full,
        )
