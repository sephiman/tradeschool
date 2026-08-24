# SPDX-License-Identifier: AGPL-3.0-only
"""Pattern injectors (§3.3): force a didactic feature onto a base path and know where it was planted.

`RsiDivergenceInjector` builds a control-point shape encoding the divergence by construction, adds
drift-free noise, then verifies the relationship holds at the swings — retrying with less noise.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.engine import regime_sigma, trend_walk_close
from tradeschool.exercises.charts.indicators import macd, rsi
from tradeschool.exercises.charts.numerics import detrend_linear
from tradeschool.exercises.charts.types import DivergenceType

Floats = NDArray[np.float64]

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

# Warm-up candles generated *before* the visible window purely so RSI/MACD are converged at the
# left edge. They are dropped from what the learner sees (real charts never show indicator warm-up).
WARMUP = 30

# Every chart (whatever the label) ends with this many candles of drift-free ambient noise at a
# FIXED volatility. The resolution is never on screen, and the last candles are drawn from the same
# distribution for every label — neither their direction nor their size can betray the answer. The
# volatility is fixed (not derived from the body) because `none` bodies are systematically choppier
# than divergence bodies, so a body-derived tail would itself leak the label.
TAIL = 8
_TAIL_SIGMA = 0.009  # ~0.9%/candle — realistic continuation volatility, no spikes
_TAIL_REVERT = 0.4  # mean-revert toward the last level so the tail consolidates, never trends off

# (fraction, log-offset) control points per divergence type, over the VISIBLE window, plus swing
# fractions and swing kind. Detection-exercise-safe by construction:
#   1. Minor pullbacks inside each leg, so no run is monotonic — RSI never pegs.
#   2. The second swing sits near the right edge and the shape is FLAT afterwards (constant at the
#      swing level). Combined with the uniform ambient TAIL, the candles after the swing carry no
#      directional "confirmation" move — the resolution is never on screen (§ rounds 2 & 6).
# Divergence is guaranteed: the second swing is a clear new extreme reached on a gentler leg (lower
# momentum), and the separations dwarf any added noise.
_SHAPES: dict[DivergenceType, tuple[list[tuple[float, float]], float, float, str]] = {
    DivergenceType.BEARISH_REGULAR: (
        [(0.00, 0.00), (0.15, 0.01), (0.25, 0.03), (0.34, 0.09), (0.42, 0.15), (0.46, 0.17),
         (0.54, 0.12), (0.62, 0.14), (0.70, 0.155), (0.78, 0.175), (0.86, 0.195), (0.90, 0.205),
         (1.00, 0.205)],
        0.46, 0.90, "high",
    ),
    DivergenceType.BULLISH_REGULAR: (
        [(0.00, 0.00), (0.15, -0.01), (0.25, -0.03), (0.34, -0.09), (0.42, -0.15), (0.46, -0.17),
         (0.54, -0.12), (0.62, -0.14), (0.70, -0.155), (0.78, -0.175), (0.86, -0.195), (0.90, -0.205),
         (1.00, -0.205)],
        0.46, 0.90, "low",
    ),
    DivergenceType.BULLISH_HIDDEN: (
        [(0.00, 0.02), (0.08, 0.06), (0.16, 0.09), (0.24, 0.065), (0.33, 0.04), (0.42, 0.10),
         (0.50, 0.15), (0.58, 0.185), (0.64, 0.20), (0.72, 0.15), (0.80, 0.12), (0.88, 0.11),
         (1.00, 0.11)],
        0.33, 0.88, "low",
    ),
    DivergenceType.BEARISH_HIDDEN: (
        [(0.00, -0.02), (0.08, -0.06), (0.16, -0.09), (0.24, -0.065), (0.33, -0.04), (0.42, -0.10),
         (0.50, -0.15), (0.58, -0.185), (0.64, -0.20), (0.72, -0.15), (0.80, -0.12), (0.88, -0.11),
         (1.00, -0.11)],
        0.33, 0.88, "high",
    ),
}

_PRICE_MARGIN = 0.004  # swings must differ by at least this fraction to read clearly
_RSI_MARGIN = 2.0
_MACD_MARGIN_FRAC = 0.0005  # of price


class DivergenceUnplantable(RuntimeError):
    """The requested divergence could not be realized on the chosen oscillator for this seed."""


class PatternInjector(ABC):
    @abstractmethod
    def build(
        self, rng: np.random.Generator, n: int, target: DivergenceType, indicator: str
    ) -> tuple[Floats, int, int | None, int | None]:
        """Return (close_full, warmup, swing1, swing2) — swings in `close_full` coords, or None."""


def _indicator_series(close: Floats, indicator: str) -> Floats:
    if indicator == "macd":
        line, _, _ = macd(close)
        return line
    return rsi(close)


def _smooth(values: Floats, window: int = 3) -> Floats:
    # Edge-pad before smoothing. `mode="same"` zero-pads the boundaries, which would drag the last
    # shape value toward 0 — and since the shape's sign encodes the pattern, that produced a large
    # final candle in the resolution direction (a didactic leak). Edge padding keeps the ends put.
    pad = window // 2
    padded = np.pad(values, pad, mode="edge")
    kernel = np.ones(window) / window
    return np.convolve(padded, kernel, mode="valid")


def _resolve_swing(close: Floats, idx: int, kind: str, w: int = 3) -> int:
    lo = max(0, idx - w)
    hi = min(len(close), idx + w + 1)
    segment = close[lo:hi]
    offset = int(np.argmax(segment) if kind == "high" else np.argmin(segment))
    return lo + offset


def _with_warmup(rng: np.random.Generator, close_visible: Floats) -> Floats:
    """Prepend WARMUP hidden candles to converge the oscillators."""
    walk = np.cumsum(rng.normal(0.0, 0.008, WARMUP + 1))
    walk = walk - walk[-1]  # end the warm-up at ~close_visible[0]
    warm = close_visible[0] * np.exp(walk[:WARMUP])
    return np.concatenate([warm, close_visible])


def _apply_ambient_tail(rng: np.random.Generator, close: Floats) -> None:
    """Overwrite the last TAIL candles in place with signal-free noise, identical for every label."""
    n = len(close)
    core = n - TAIL
    if core < 20:
        return
    anchor = float(np.log(close[core - 1]))  # consolidate around the last real level
    for k in range(core, n):
        prev = float(np.log(close[k - 1]))
        drift = _TAIL_REVERT * (anchor - prev)  # symmetric pull-back — no directional bias
        close[k] = float(np.exp(prev + drift + rng.normal(0.0, _TAIL_SIGMA)))


def _relationship_ok(
    target: DivergenceType, close: Floats, ind: Floats, s1: int, s2: int, indicator: str
) -> bool:
    price_margin = _PRICE_MARGIN * close[s1]
    ind_margin = _MACD_MARGIN_FRAC * close[s1] if indicator == "macd" else _RSI_MARGIN
    higher_price = bool(close[s2] > close[s1] + price_margin)
    lower_price = bool(close[s2] < close[s1] - price_margin)
    higher_ind = bool(ind[s2] > ind[s1] + ind_margin)
    lower_ind = bool(ind[s2] < ind[s1] - ind_margin)
    if target == DivergenceType.BEARISH_REGULAR:
        return higher_price and lower_ind
    if target == DivergenceType.BULLISH_REGULAR:
        return lower_price and higher_ind
    if target == DivergenceType.BULLISH_HIDDEN:
        return higher_price and lower_ind
    if target == DivergenceType.BEARISH_HIDDEN:
        return lower_price and higher_ind
    return False


class RsiDivergenceInjector(PatternInjector):
    def build(
        self, rng: np.random.Generator, n: int, target: DivergenceType, indicator: str
    ) -> tuple[Floats, int, int | None, int | None]:
        base_price = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))

        if target == DivergenceType.NONE:
            close_visible = trend_walk_close(rng, n, base_price, regime_sigma(rng, n))
            _apply_ambient_tail(rng, close_visible)
            return _with_warmup(rng, close_visible), WARMUP, None, None

        points, f1, f2, kind = _SHAPES[target]
        i1, i2 = int(f1 * n), int(f2 * n)
        xs = [p[0] * (n - 1) for p in points]
        ys = [p[1] for p in points]
        x = np.arange(n, dtype=float)
        shape = _smooth(np.interp(x, xs, ys))

        def assemble(close_visible: Floats) -> tuple[Floats, int, int]:
            full = _with_warmup(rng, close_visible)
            s1 = WARMUP + _resolve_swing(close_visible, i1, kind)
            s2 = WARMUP + _resolve_swing(close_visible, i2, kind)
            return full, s1, s2

        def verified(full: Floats, s1: int, s2: int) -> bool:
            ind = _indicator_series(full, indicator)
            return s1 != s2 and _relationship_ok(target, full, ind, s1, s2, indicator)

        sigma0 = 0.007
        for attempt in range(7):
            step_sigma = sigma0 * (0.6**attempt)
            walk = np.cumsum(rng.normal(0.0, step_sigma, n))
            # Detrend (remove the noise's own net drift) but keep variance everywhere, so the
            # candles never go dead-flat at the ends. `detrend_linear`, not `np.polyfit`: the latter
            # solved this through LAPACK (see `charts/numerics.py`).
            noise = detrend_linear(x, walk)
            close_visible = np.exp(np.log(base_price) + shape + noise)
            _apply_ambient_tail(rng, close_visible)
            full, s1, s2 = assemble(close_visible)
            if verified(full, s1, s2):
                return full, WARMUP, s1, s2

        # Last resort: the pure shape (no noise), which encodes the divergence by construction and
        # is already wavy enough not to peg. Still verified — we never return a chart whose
        # oscillator disagrees with the label. RSI shapes always satisfy this; MACD is best-effort.
        close_visible = np.exp(np.log(base_price) + shape)
        _apply_ambient_tail(rng, close_visible)
        full, s1, s2 = assemble(close_visible)
        if verified(full, s1, s2):
            return full, WARMUP, s1, s2
        raise DivergenceUnplantable(f"could not plant {target.value} on {indicator}")
