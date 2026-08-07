# SPDX-License-Identifier: AGPL-3.0-only
"""Base price engine: derive believable OHLC candles and correlated volume from a close path.

Float is fine here — this is scenario data, not a graded financial figure (§8).
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.types import Series

Floats = NDArray[np.float64]

START_TIME = 1_700_000_000
INTERVAL = 86400  # daily bars — the timeframe is abstract; daily gives a clean, non-repeating axis


def _rolling_std(values: Floats, window: int) -> Floats:
    out = np.empty_like(values)
    for i in range(len(values)):
        lo = max(0, i - window + 1)
        out[i] = values[lo : i + 1].std()
    return out


def regime_sigma(rng: np.random.Generator, n: int, base: float = 0.012) -> Floats:
    """Per-bar volatility with a few regimes (calm/volatile stretches)."""
    n_regimes = int(rng.integers(2, 4))
    bounds = np.linspace(0, n, n_regimes + 1).astype(int)
    sigma = np.empty(n)
    for r in range(n_regimes):
        mult = float(rng.uniform(0.6, 1.8))
        sigma[bounds[r] : bounds[r + 1]] = base * mult
    return sigma


def random_walk_close(
    rng: np.random.Generator, n: int, base_price: float, drift: float, sigma: Floats
) -> Floats:
    returns = rng.normal(drift, sigma, n)
    return base_price * np.exp(np.cumsum(returns))


def trend_walk_close(rng: np.random.Generator, n: int, base_price: float, sigma: Floats) -> Floats:
    """A walk with a few drift regimes, so RSI genuinely reaches oversold/overbought during a trend."""
    regimes = int(rng.integers(2, 5))
    bounds = np.linspace(0, n, regimes + 1).astype(int)
    drift = np.zeros(n)
    for r in range(regimes):
        mode = rng.integers(0, 3)  # 0 up, 1 down, 2 range
        if mode == 0:
            d = float(rng.uniform(0.0025, 0.006))
        elif mode == 1:
            d = -float(rng.uniform(0.0025, 0.006))
        else:
            d = float(rng.uniform(-0.0006, 0.0006))
        drift[bounds[r] : bounds[r + 1]] = d
    return base_price * np.exp(np.cumsum(rng.normal(drift, sigma)))


def build_series(
    rng: np.random.Generator,
    close: Floats,
    *,
    base_volume: float = 1000.0,
    wick_scale: float = 0.8,
) -> Series:
    n = len(close)
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]

    logret = np.diff(np.log(close), prepend=np.log(close[0]))
    localvol = np.maximum(_rolling_std(logret, 6), 0.004)

    body_hi = np.maximum(open_, close)
    body_lo = np.minimum(open_, close)
    up = np.abs(rng.normal(0.0, 1.0, n)) * localvol * wick_scale
    dn = np.abs(rng.normal(0.0, 1.0, n)) * localvol * wick_scale
    high = body_hi * (1.0 + up)
    low = body_lo * (1.0 - dn)

    vol_noise = np.exp(rng.normal(0.0, 0.25, n))
    volume = base_volume * (0.6 + 3.5 * np.abs(logret) / (localvol + 1e-9)) * vol_noise

    times = [START_TIME + i * INTERVAL for i in range(n)]
    return Series(
        time=times,
        open=[round(x, 2) for x in open_.tolist()],
        high=[round(x, 2) for x in high.tolist()],
        low=[round(x, 2) for x in low.tolist()],
        close=[round(x, 2) for x in close.tolist()],
        volume=[round(x, 2) for x in volume.tolist()],
    )
