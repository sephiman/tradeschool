# SPDX-License-Identifier: AGPL-3.0-only
"""Liquidity-sweep injector (m19-l2 and m06-l1): the shelf, the wick through it, the snap-back.

The geometry is identical across labels on purpose — it is one event, and sharing an injector is what
keeps the two lessons from teaching two different shapes for it. Only the annotation and spike size
differ, which is the difference in emphasis between the two passages.

The sweep is a planted WICK (`candles_full`), not a close-path excursion: the body stayed above the
shelf and only the wick went through. Classification injector — no hidden future to leak.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    Level,
    LevelGuard,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    clamp_close_inside,
    resolve_swing,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# Prices are log distances from the SHELF (offset 0) — the low that held, which is the price the whole
# picture is built from.
_HOLD_F = (0.22, 0.48)  # the two holds that make the shelf a shelf
_PLATEAU = 0.020
_APPROACH_F = 0.72  # price comes back to the shelf a third time
_SWEEP_F = 0.80  # the sweep bar
_SWEEP_CLOSE = 0.010  # where the sweep bar CLOSES: back above the shelf, which is the reclaim
_DEPTH = 0.022  # how far the wick reaches below the shelf — the pocket that got taken
# Volume on the sweep bar, as a multiple of the chart's median. The sweep is a burst of forced flow, so
# it prints a bar unlike any other; the cascade figure leans on that harder because m06-l1's point is
# that the spike IS the forced closing and not fresh conviction.
_SPIKE = {"liquidity_sweep": 4.0, "liquidation_cascade": 7.0}
_NOISE = 0.004


class LiquiditySweepInjector(PatternInjector):
    name: ClassVar[str] = "liquidity_sweep"
    labels: ClassVar[tuple[str, ...]] = ("liquidity_sweep", "liquidation_cascade")
    hides_resolution: ClassVar[bool] = False  # the sweep and its reclaim are both on screen
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in _SPIKE:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown liquidity_sweep label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        def hold(f: float) -> list[tuple[float, float]]:
            """A hold of the shelf: price sits on it for a few bars and turns up."""
            return [(f - _PLATEAU, 0.006), (f + _PLATEAU, 0.006)]

        pts: list[tuple[float, float]] = [
            (0.00, 0.055), (0.10, 0.030),
            *hold(_HOLD_F[0]),
            (0.34, 0.040),
            *hold(_HOLD_F[1]),
            (0.60, 0.035),
            (_APPROACH_F, 0.010),  # the third approach — the one that gets taken through
            (_SWEEP_F, _SWEEP_CLOSE),
            # The snap-back, far enough above the shelf that the ambient tail cannot wander back down to
            # it: "reclaimed within a candle or two" is the tell that separates a sweep from a break.
            (0.87, 0.032),
            (0.94, 0.048),
            (1.00, 0.055),
        ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=_NOISE))
        apply_ambient_tail(rng, close_visible)
        # The shelf HELD: every close in the window is above it, all the way through the sweep — only the
        # wick went below, which is the difference between a sweep and a break (m19-l2's own tell).
        clamp_close_inside(close_visible, round(base, 2), "support")
        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        shelf = round(base, 2)
        w_full = WARMUP + int(_SWEEP_F * n)
        # The planted wick and the volume that came with it. `build_series` draws wicks from a half-normal
        # and volume from the bar's own move, so a sweep left to it is an ordinary bar; both are the
        # signature of the event and both are planted here.
        series.low[w_full] = round(base * float(np.exp(-_DEPTH)), 2)
        # Sized against the VISIBLE window's median, which is the only volume a learner can compare it to.
        series.volume[w_full] = round(float(np.median(series.volume[WARMUP:])) * _SPIKE[target], 2)

        hold_tests = tuple(
            WARMUP + resolve_swing(close_visible, int(f * n), "low", w=int(_PLATEAU * n)) + off
            for f in (*_HOLD_F, _APPROACH_F)
            for off in (0, 1)
        )
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[
                Annotation(
                    index=w_full,
                    kind="low",
                    label="sweep" if target == "liquidity_sweep" else "liquidation",
                )
            ],
            levels=[Level(price=shelf, label="shelf", kind="support")],
            level_guards=[
                # The shelf is tested three times and breached by exactly one bar: the sweep. Everything
                # else — before and after — holds above it, which is what makes the wick read as a raid on
                # the pocket rather than as the level giving way.
                LevelGuard(
                    shelf,
                    "support",
                    tests=hold_tests,
                    no_breach=((0, w_full), (w_full + 1, len(close_full))),
                )
            ],
            candles_full=series,
            resolution_hint=1.0,
        )
