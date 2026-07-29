# SPDX-License-Identifier: AGPL-3.0-only
"""Shared, gate-vetted anti-leak primitives for pattern injectors.

These are an independent copy of the machinery proven on the Phase-1 divergence injector (the frozen
`charts/injectors.py` is left untouched, per the freeze). Every Phase-2 injector composes from these
so it inherits the same guarantees: indicator warm-up is generated then hidden, control-point shapes
are smoothed without a boundary artifact, and the visible window ends in drift-free ambient noise so
the resolution is never on screen and the last candles cannot betray the label.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.patterns.base import LevelGuard
from tradeschool.exercises.charts.types import Series

Floats = NDArray[np.float64]

# Warm-up candles generated BEFORE the visible window so RSI/MACD are converged at the left edge.
# Dropped from what the learner sees (real charts never show indicator warm-up).
WARMUP = 30

# The visible window ends with this many candles of drift-free, mean-reverting ambient noise at a
# FIXED volatility — identical distribution for every label, so neither the size nor the direction of
# the final candles can leak the answer, and no synthetic-looking spike appears (Phase-1 round 6).
TAIL = 8
TAIL_SIGMA = 0.009  # ~0.9%/candle — realistic continuation volatility, no spikes
TAIL_REVERT = 0.4  # mean-revert toward the last real level so the tail consolidates, never trends off


def smooth(values: Floats, window: int = 3) -> Floats:
    """Moving-average smoothing with EDGE padding. `mode="same"` zero-pads the boundaries, which
    drags the last shape value toward 0; since a shape's sign encodes the pattern, that produced a
    large final candle in the resolution direction (a leak). Edge padding keeps the ends put."""
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def shape_from_points(points: list[tuple[float, float]], n: int) -> Floats:
    """Interpolate (fraction-of-window, log-offset) control points onto an n-length log-offset curve,
    then smooth. The curve is added to a log base price to build a close path with a designed shape."""
    xs = [p[0] * (n - 1) for p in points]
    ys = [p[1] for p in points]
    x = np.arange(n, dtype=float)
    return smooth(np.interp(x, xs, ys))


def detrended_noise(rng: np.random.Generator, n: int, sigma: float) -> Floats:
    """A driftless Brownian-bridge-ish noise path: a random walk with its own net linear drift
    removed, so variance stays everywhere (candles never go dead-flat) but the noise adds no trend."""
    walk = np.cumsum(rng.normal(0.0, sigma, n))
    x = np.arange(n, dtype=float)
    return walk - np.polyval(np.polyfit(x, walk, 1), x)


def bounded_noise(rng: np.random.Generator, n: int, amp: float, base_sigma: float = 0.006) -> Floats:
    """Correlated candle texture (a detrended walk) rescaled so its PEAK absolute excursion equals
    `amp`. A raw walk's mid-path excursions (~sigma*sqrt(n)) can rival a pattern's designed separations and
    accidentally cross a level; bounding the peak keeps the texture without ever faking the pattern."""
    noise = detrended_noise(rng, n, base_sigma)
    peak = float(np.max(np.abs(noise)))
    return noise * (amp / peak) if peak > 0 else noise


def with_warmup(
    rng: np.random.Generator, close_visible: Floats, drift: float = 0.0, sigma: float = 0.008
) -> Floats:
    """Prepend WARMUP gentle candles that connect into the visible series purely to converge the
    oscillators. Dropped from what the learner sees.

    `drift` ramps the warm-up in log-price so it *arrives* already trending (it starts `drift` below
    the visible open and ends at it), and `sigma` sets its candle noise. Both default to the original
    flat, driftless walk, so every existing injector is byte-identical. They exist for the one case
    where the visible reading needs the indicator to ALREADY have a settled sign at the left edge:
    m11's MACD crossovers, where a flat warm-up leaves the MACD line wandering across zero there and
    would show a stray crossing the label never claimed.
    """
    walk = np.cumsum(rng.normal(0.0, sigma, WARMUP + 1))
    walk = walk - walk[-1]  # end the warm-up at ~close_visible[0]
    if drift:
        walk = walk + drift * (np.linspace(0.0, 1.0, WARMUP + 1) - 1.0)
    warm = close_visible[0] * np.exp(walk[:WARMUP])
    return np.concatenate([warm, close_visible])


def apply_ambient_tail(rng: np.random.Generator, close: Floats, tail: int = TAIL) -> None:
    """Overwrite the last `tail` candles (in place) with drift-free, mean-reverting noise at the fixed
    ambient volatility, for EVERY label. No resolution or confirmation move is shown; the final
    candles carry no directional signal that could betray the label."""
    n = len(close)
    core = n - tail
    if core < 20:
        return
    anchor = float(np.log(close[core - 1]))  # consolidate around the last real level
    for k in range(core, n):
        prev = float(np.log(close[k - 1]))
        drift = TAIL_REVERT * (anchor - prev)  # symmetric pull-back — no directional bias
        close[k] = float(np.exp(prev + drift + rng.normal(0.0, TAIL_SIGMA)))


def append_resolution(
    rng: np.random.Generator, close: Floats, direction: float, strength: float = 0.18, length: int = 24
) -> Floats:
    """Append `length` candles continuing the story — the pattern's RESOLUTION — for lesson FIGURES
    only (never exercises, which stop before it). `direction` is +1 up / -1 down / 0 sideways; a
    directional leg moves ~`strength` in log-price with believable texture, a sideways leg consolidates
    around the last level. Purely additive: it extends an already-built close path and never feeds back
    into an injector's `build()`."""
    start = float(np.log(close[-1]))
    if direction == 0:
        leg = np.empty(length)
        prev = start
        for k in range(length):
            prev = prev + TAIL_REVERT * (start - prev) + float(rng.normal(0.0, 0.008))
            leg[k] = float(np.exp(prev))
        return np.concatenate([close, leg])
    ramp = direction * strength * np.linspace(0.0, 1.0, length)
    leg = np.exp(start + ramp + bounded_noise(rng, length, amp=0.012))
    return np.concatenate([close, leg])


def append_linear_continuation(
    rng: np.random.Generator, values: Floats, direction: float, strength: float, length: int
) -> Floats:
    """`append_resolution` for a series that lives in LINEAR space and may sit at or below zero.

    The price/OI version builds its leg as ``exp(log(last) + ramp)``, which is meaningless for a
    cumulative volume delta: a CVD is a running sum of signed flow anchored at 0, so it is routinely
    negative and ``log`` of it is not a number. Here the leg is a straight ramp of `strength` x the
    series' own visible amplitude, plus proportional texture. Figure-only, like `append_resolution`.
    """
    last = float(values[-1])
    span = float(np.max(values) - np.min(values))
    scale = span if span > 0 else max(abs(last), 1.0)
    if direction == 0:
        leg = last + rng.normal(0.0, 0.02 * scale, length)
        return np.concatenate([values, leg])
    ramp = direction * strength * scale * np.linspace(0.0, 1.0, length)
    leg = last + ramp + rng.normal(0.0, 0.02 * scale, length)
    return np.concatenate([values, leg])


# How far past a level a planted test wick reaches: 0.08% of the price — enough that the bar's range
# provably straddles the line at every base price scale (values are rounded to 2dp), small enough to
# read as a touch rather than a break.
LEVEL_GRAZE = 0.0008


def clamp_close_inside(
    close: Floats, price: float, kind: str, start: int = 0, inset: float = 0.0015
) -> None:
    """Hold a close path on the inside of a level from `start` on.

    `LevelGuard` can only move wicks — a body is the close path the indicators are derived from — so a
    level that must never be breached needs the close path itself bounded. The offender is the ambient
    tail: it is a driftless random walk, so over eight candles it can wander through a bound the label
    says was never broken and print the very break the chart denies (6% of plain `wyckoff` ranges did).
    The tail is signal-free by construction — the same distribution for every label — so bounding it
    costs nothing didactically and turns "almost never breached" into "never". `inset` keeps a clamped
    close a hair inside the line, so the level stays the wick's territory rather than the body's.
    """
    limit = price * (1.0 - inset) if kind == "resistance" else price * (1.0 + inset)
    tail = close[start:]
    if kind == "resistance":
        np.minimum(tail, limit, out=tail)
    else:
        np.maximum(tail, limit, out=tail)


def apply_level_guards(series: Series, guards: Iterable[LevelGuard]) -> None:
    """Make the candles honour every drawn level — the single enforcement point for the invariant that
    a drawn level is a price the visible action actually respects.

    Called by the exercise generator AND the figure builder, so the two can never disagree about what
    a level means. `tests` bars get their wick extended to the line; `no_breach` spans get breaching
    wicks clamped back to it. A test bar that also sits inside a `no_breach` span ends up topping out
    exactly ON the level — which is what a tested-but-unbroken level looks like.

    Only wicks move. A body is the close path the indicators are derived from, so it is untouchable;
    a body on the wrong side of a level is left visible for the level tests to fail on rather than
    quietly papered over here.
    """
    for g in guards:
        up = g.kind == "resistance"  # "beyond" is above for a resistance, below for a support
        edge = series.high if up else series.low
        for j in g.tests:
            if not 0 <= j < len(edge):
                continue
            reach = g.price * (1.0 + LEVEL_GRAZE) if up else g.price * (1.0 - LEVEL_GRAZE)
            edge[j] = round(max(edge[j], reach) if up else min(edge[j], reach), 2)
        for lo, hi in g.no_breach:
            for j in range(max(0, lo), min(hi, len(edge))):
                body = (
                    max(series.open[j], series.close[j]) if up else min(series.open[j], series.close[j])
                )
                limit = max(g.price, body) if up else min(g.price, body)
                edge[j] = round(min(edge[j], limit) if up else max(edge[j], limit), 2)


def resolve_swing(close: Floats, idx: int, kind: str, w: int = 3) -> int:
    """The real local extreme nearest a designed swing index (the noise can shift it by a candle)."""
    lo = max(0, idx - w)
    hi = min(len(close), idx + w + 1)
    segment = close[lo:hi]
    offset = int(np.argmax(segment) if kind == "high" else np.argmin(segment))
    return lo + offset


def candle_extreme(series: Series, lo: int, hi: int, kind: str) -> int:
    """The bar with the highest high / lowest low in `[lo, hi)` — a pivot anchored to the CANDLES.

    `resolve_swing` answers the same question on the close path, which is where an injector's designed
    shape lives, and that is the right anchor for a swing the shape defines. But a pivot LABEL ("this
    bar is the higher high") is read off the wicks, and `build_series` draws every wick from a
    half-normal: the close-path extreme and the candle extreme land a bar or two apart, which puts the
    label beside the visibly highest bar instead of on it.

    Taking the extreme over a whole swing SEGMENT — bounded by the neighbouring opposite pivots, not by
    a few bars either side of a designed index — makes the marked bar the extreme of its swing by
    construction. That is what lets the annotation tests assert extremality outright instead of
    tolerating a near-miss, and near-misses are the whole problem: on a plateaued pivot the difference
    between the marked bar and its neighbour is one wick draw, so any tolerance is arbitrary.
    """
    lo = max(0, lo)
    hi = min(len(series.close), hi)
    edge = series.high if kind == "high" else series.low
    window = np.asarray(edge[lo:hi], dtype=float)
    offset = int(np.argmax(window) if kind == "high" else np.argmin(window))
    return lo + offset
