# SPDX-License-Identifier: AGPL-3.0-only
"""Candle-reaction injector (module m08-l2): a single formation at the right edge, cut BEFORE it
resolves. A candle is the footprint of order flow, and two mechanics wear many names:

* **rejection** — a long wick: price was pushed to a price, absorbed, and returned (hammer at lows,
  shooting star at highs, tweezers = double rejection).
* **overrun** — an engulfing body: one side steamrolled the other and invalidated the prior range
  (a morning/evening star tells the same across three candles; a harami is the compression after).
* **non-information** — a doji (nobody won) or a small-range candle (compression): no signal.

The governing rule the exercise tests: **location is 90% of the signal.** The same form at a drawn
level is information; in open space it is noise. This is a *classification* injector — the label IS
the visible state (form + location), so ``hides_resolution`` is False; there is no hidden future to
leak. "Cut before resolution" means the reaction is the final candle(s); what happens next is off
screen. build_series randomizes wicks, so this injector ships its own OHLC via ``candles_full`` to
plant the wick/body precisely; the reaction's close move stays well under the credibility spike bound.
"""

from __future__ import annotations

from dataclasses import dataclass
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
    resolve_swing,
    shape_from_points,
    with_warmup,
)

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_GAP = 0.05  # log-distance from the range midline to the level
_TOUCH_F = 0.46  # where the approach makes its prior touch of the level (see the shape below)
# How far PAST a drawn level a rejection wick reaches before price returns. Anchoring the tip to the
# line rather than to a fixed fraction of the close is what makes the rejection legible, but the tip
# must clear the line by enough that the candle still reads as a long wick (the approach already sits
# only `_GAP - 0.012` inside it), and a wick that pierces the level and closes back is the textbook
# form — a hammer's spring below support, a shooting star's raid above resistance.
_PIERCE = 0.012


@dataclass(frozen=True)
class _Form:
    """A concrete formation: per-bar body moves (log returns) for the trailing reaction candles,
    optional wick plants, the level side it belongs at, and which reaction bar to mark."""

    name: str
    deltas: tuple[float, ...]
    wicks: tuple[tuple[int, str, float], ...]  # (bar offset, "low"|"high"|"clamp", fraction)
    side: str | None  # "support" | "resistance" | None (open space / non-information)
    marker: int  # index within the reaction bars to annotate


# The named forms of the dictionary, each an expression of the two mechanics at a location.
_FORMS: dict[str, _Form] = {
    "hammer": _Form("hammer", (0.003,), ((0, "low", 0.040),), "support", 0),
    "shooting_star": _Form("shooting_star", (-0.003,), ((0, "high", 0.040),), "resistance", 0),
    "bullish_engulfing": _Form("bullish_engulfing", (-0.013, 0.030), (), "support", 1),
    "bearish_engulfing": _Form("bearish_engulfing", (0.013, -0.030), (), "resistance", 1),
    "morning_star": _Form("morning_star", (-0.028, 0.0008, 0.028), (), "support", 2),
    "evening_star": _Form("evening_star", (0.028, -0.0008, -0.028), (), "resistance", 2),
    "harami": _Form("harami", (0.030, -0.004), (), None, 1),
    "tweezers_bottom": _Form(
        "tweezers_bottom", (0.002, 0.003), ((0, "low", 0.034), (1, "low", 0.034)), "support", 1
    ),
    "tweezers_top": _Form(
        "tweezers_top", (-0.002, -0.003), ((0, "high", 0.034), (1, "high", 0.034)), "resistance", 1
    ),
    "doji": _Form("doji", (0.0006,), ((0, "low", 0.012), (0, "high", 0.012)), None, 0),
    "small_range": _Form("small_range", (0.0008,), ((0, "clamp", 0.004),), None, 0),
}

# Figure-only: the direction the reaction resolves into (+1 bounce up / -1 drop down / 0 nothing).
# A rejection at support bounces; a shooting star at resistance drops; a doji/small-range and a form
# in open space resolve into nothing directional — which the centered figure shows honestly.
_RESOLUTION_DIR: dict[str, float] = {
    "hammer": 1.0,
    "shooting_star": -1.0,
    "bullish_engulfing": 1.0,
    "bearish_engulfing": -1.0,
    "morning_star": 1.0,
    "evening_star": -1.0,
    "tweezers_bottom": 1.0,
    "tweezers_top": -1.0,
    "harami": 0.0,
    "doji": 0.0,
    "small_range": 0.0,
}

# The judgment labels the exercise grades (form + location → what it means here). Each picks one of
# a few forms so retakes vary; the takeaway is the location, not the individual candle.
_JUDGMENT: dict[str, tuple[str, ...]] = {
    "rejection_at_level": ("hammer", "shooting_star"),
    "overrun_at_level": ("bullish_engulfing", "bearish_engulfing"),
    "open_space": ("hammer", "shooting_star", "bullish_engulfing", "bearish_engulfing"),
    "indecision": ("doji", "small_range"),
}


class CandleReactionInjector(PatternInjector):
    name: ClassVar[str] = "candle_reaction"
    labels: ClassVar[tuple[str, ...]] = (
        # Exercise judgment labels (targets/choices are drawn from these):
        "rejection_at_level",
        "overrun_at_level",
        "open_space",
        "indecision",
        # Figure-only named forms of the dictionary:
        *tuple(_FORMS),
    )
    hides_resolution: ClassVar[bool] = False  # the label is the visible form+location, not a future
    indicator: ClassVar[str] = "none"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        form, at_level = self._resolve_form(rng, target)
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        k = len(form.deltas)

        # Approach: a gentle range that (at a level) demonstrates the level with a prior touch, then
        # comes to it just before the reaction; in open space, a drift with no structure to lean on.
        sign = -1.0 if form.side == "support" else 1.0
        if at_level and form.side is not None:
            approach_end = sign * (_GAP - 0.012)  # sit just inside the level before the reaction
            pts = [
                (0.00, 0.0), (0.14, sign * 0.010), (0.30, -sign * 0.006),
                (_TOUCH_F, sign * (_GAP - 0.006)),  # prior touch near the level
                (0.60, -sign * 0.004), (0.74, sign * 0.008), (0.90, approach_end),
            ]
        else:  # open space / non-information: no level, gentle wander around the midline
            approach_end = float(rng.uniform(-0.008, 0.008))
            pts = [
                (0.00, 0.0), (0.18, 0.012), (0.36, -0.010), (0.54, 0.008),
                (0.72, -0.006), (0.90, approach_end),
            ]
        shape = shape_from_points(pts, n)
        close_visible = base * np.exp(shape)

        # Crisp reaction bodies at the very end (no smoothing across them) — build_series turns each
        # body move into a candle whose open is the prior close.
        for i, d in enumerate(form.deltas):
            idx = n - k + i
            close_visible[idx] = close_visible[idx - 1] * float(np.exp(d))

        close_full = with_warmup(rng, close_visible)
        series = build_series(rng, close_full)

        # Plant the wicks build_series randomized: extend a rejection wick, or clamp a small range.
        full_k0 = len(close_full) - k
        # At a drawn level the rejection wick is anchored to THAT LINE — "price was pushed to a price,
        # absorbed, and returned" is only legible if the tip lands on the price the chart draws. A
        # fixed fraction of the close (what open-space forms still use, having no line to reach) put
        # the tip an arbitrary distance past it.
        level_price = round(base * float(np.exp(sign * _GAP)), 2) if at_level and form.side else None
        for bar, side, frac in form.wicks:
            j = full_k0 + bar
            c = series.close[j]
            o = series.open[j]
            hi, lo = max(o, c), min(o, c)
            if side == "low":
                tip = level_price * (1.0 - _PIERCE) if level_price else c * (1.0 - frac)
                series.low[j] = round(min(series.low[j], tip), 2)
            elif side == "high":
                tip = level_price * (1.0 + _PIERCE) if level_price else c * (1.0 + frac)
                series.high[j] = round(max(series.high[j], tip), 2)
            else:  # clamp — a genuinely small-range candle (compression): tiny body, tiny wicks
                series.high[j] = round(hi * (1.0 + frac), 2)
                series.low[j] = round(lo * (1.0 - frac), 2)

        # Ground-truth annotation on the decisive reaction bar (visible coords via the generator).
        marker_full = full_k0 + form.marker
        annotations = [Annotation(index=marker_full, kind="marker", label=form.name)]

        levels: list[Level] = []
        guards: list[LevelGuard] = []
        if level_price is not None and form.side is not None:
            # The level is the price the APPROACH was built against — `_GAP` from the range midline,
            # the same constant the prior touch (`_GAP - 0.006`) and the pre-reaction approach
            # (`_GAP - 0.012`) are written from. It used to be read off the reaction candles' own wick
            # extreme instead, which put the line 3-4% beyond every bar that was supposed to establish
            # it: the drawn level was tangent to exactly one candle (the reaction's own wick, by
            # construction) and the prior touch never reached it. Deriving it from `_GAP` is what makes
            # the line the price the chart visibly respects.
            levels = [Level(price=level_price, label=form.side, kind=form.side)]
            touch_kind = "low" if form.side == "support" else "high"
            guards = [
                LevelGuard(
                    price=level_price,
                    kind=form.side,
                    # The prior touch and the last approach bar must reach the line, so it is drawn
                    # where price has actually been rather than in empty space.
                    tests=(
                        WARMUP + resolve_swing(close_visible, int(_TOUCH_F * n), touch_kind),
                        full_k0 - 1,
                    ),
                    # Before the reaction, the level holds — that is the premise the reaction is read
                    # against. The reaction bars themselves are exempt: a rejection wick piercing the
                    # line and a bullish engulfing's first bar dipping under it are the whole point.
                    no_breach=((0, full_k0),),
                )
            ]

        # In open space / indecision the honest payload is that nothing directional follows.
        hint = 0.0 if target in ("open_space", "indecision") else _RESOLUTION_DIR.get(form.name, 0.0)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=annotations,
            levels=levels,
            level_guards=guards,
            candles_full=series,
            resolution_hint=hint,
        )

    def _resolve_form(self, rng: np.random.Generator, target: str) -> tuple[_Form, bool]:
        """Map a target to a concrete form and whether a level is drawn. Judgment targets sample a
        form (and 'at level' for all but open space); named-form targets map directly."""
        if target in _JUDGMENT:
            choices = _JUDGMENT[target]
            form = _FORMS[choices[int(rng.integers(0, len(choices)))]]
            at_level = target in ("rejection_at_level", "overrun_at_level")
            return form, at_level
        if target in _FORMS:
            form = _FORMS[target]
            return form, form.side is not None
        raise ValueError(f"unknown candle_reaction label {target!r}")  # pragma: no cover
