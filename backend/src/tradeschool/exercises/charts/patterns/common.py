# SPDX-License-Identifier: AGPL-3.0-only
"""Shared anti-leak primitives for pattern injectors.

An independent copy of the Phase-1 machinery: the frozen `charts/injectors.py` stays untouched.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.numerics import detrend_linear
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
    """Moving-average smoothing with EDGE padding.

    Not `mode="same"`: its zero-padding drags the last shape value toward 0, leaking the resolution.
    """
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def shape_from_points(points: list[tuple[float, float]], n: int) -> Floats:
    """Interpolate (fraction-of-window, log-offset) control points onto an n-length curve, smoothed."""
    xs = [p[0] * (n - 1) for p in points]
    ys = [p[1] for p in points]
    x = np.arange(n, dtype=float)
    return smooth(np.interp(x, xs, ys))


def detrended_noise(rng: np.random.Generator, n: int, sigma: float) -> Floats:
    """A driftless noise path: a random walk with its own net linear drift removed.

    The fit is `numerics.detrend_linear`, not `np.polyfit` — the latter went through LAPACK, whose
    kernel the CPU picks at load time (see `charts/numerics.py`).
    """
    walk = np.cumsum(rng.normal(0.0, sigma, n))
    x = np.arange(n, dtype=float)
    return detrend_linear(x, walk)


def bounded_noise(rng: np.random.Generator, n: int, amp: float, base_sigma: float = 0.006) -> Floats:
    """Candle texture rescaled so its PEAK absolute excursion equals `amp`.

    Bounding the peak stops a raw walk's excursions from rivalling the pattern's own separations.
    """
    noise = detrended_noise(rng, n, base_sigma)
    peak = float(np.max(np.abs(noise)))
    return noise * (amp / peak) if peak > 0 else noise


def with_warmup(
    rng: np.random.Generator, close_visible: Floats, drift: float = 0.0, sigma: float = 0.008
) -> Floats:
    """Prepend WARMUP hidden candles to converge the oscillators before the visible window.

    `drift` makes the warm-up arrive already trending, for readings needing a settled sign at the
    left edge (m11's MACD, where a flat warm-up shows a stray crossing the label never claimed).
    """
    walk = np.cumsum(rng.normal(0.0, sigma, WARMUP + 1))
    walk = walk - walk[-1]  # end the warm-up at ~close_visible[0]
    if drift:
        walk = walk + drift * (np.linspace(0.0, 1.0, WARMUP + 1) - 1.0)
    warm = close_visible[0] * np.exp(walk[:WARMUP])
    return np.concatenate([warm, close_visible])


def apply_ambient_tail(rng: np.random.Generator, close: Floats, tail: int = TAIL) -> None:
    """Overwrite the last `tail` candles in place with signal-free noise, identical for every label."""
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
    """Append the pattern's resolution (+1 up / -1 down / 0 sideways) — FIGURES only, never exercises."""
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
    """`append_resolution` for a LINEAR series that may sit at or below zero, e.g. a CVD.

    The log-space version returns NaN there, since a CVD is signed flow anchored at 0.
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

    `LevelGuard` moves only wicks, so a never-breached level needs the close path bounded too —
    otherwise the ambient tail's random walk prints the very break the label denies.
    """
    limit = price * (1.0 - inset) if kind == "resistance" else price * (1.0 + inset)
    tail = close[start:]
    if kind == "resistance":
        np.minimum(tail, limit, out=tail)
    else:
        np.maximum(tail, limit, out=tail)


def apply_level_guards(series: Series, guards: Iterable[LevelGuard]) -> None:
    """Make the candles honour every drawn level — the single enforcement point, shared by exercises
    and figures.

    Only wicks move; a body on the wrong side is left visible for the level tests to fail on.
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

    Use this, not `resolve_swing`, to place a pivot LABEL: readers read pivots off the wicks, and the
    close-path extreme lands a bar or two away from the visibly highest one.
    """
    lo = max(0, lo)
    hi = min(len(series.close), hi)
    edge = series.high if kind == "high" else series.low
    window = np.asarray(edge[lo:hi], dtype=float)
    offset = int(np.argmax(window) if kind == "high" else np.argmin(window))
    return lo + offset
