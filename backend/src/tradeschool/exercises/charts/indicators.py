# SPDX-License-Identifier: AGPL-3.0-only
"""Indicator maths (NumPy, float — scenario data, not financial grading §8).

RSI and MACD, plus the volatility family m16 reads: Bollinger (mean ± standard deviations), Keltner
(mean ± ATR), and the squeeze momentum they are packaged into. Every one of them is defined over the
FULL series including warm-up, and every one is `len(close)` long, filled forward at the left edge so
a pane never opens on a NaN.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.numerics import rowwise_mean_and_centred_slope

Floats = NDArray[np.float64]


def ema(values: Floats, period: int) -> Floats:
    alpha = 2.0 / (period + 1.0)
    out = np.empty_like(values)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1.0 - alpha) * out[i - 1]
    return out


def rsi(close: Floats, period: int = 14) -> Floats:
    """Wilder's RSI in [0, 100], length == len(close).

    Only defined from index `period` on; earlier bars are warm-up filled with the first real value.
    """
    n = len(close)
    out = np.full(n, 50.0)
    if n <= period:
        return out

    delta = np.diff(close)  # delta[k] = close[k+1] - close[k]
    gain = np.clip(delta, 0.0, None)
    loss = -np.clip(delta, None, 0.0)

    avg_gain = float(gain[:period].mean())
    avg_loss = float(loss[:period].mean())
    out[period] = 100.0 - 100.0 / (1.0 + avg_gain / (avg_loss + 1e-12))
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gain[i - 1]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i - 1]) / period
        out[i] = 100.0 - 100.0 / (1.0 + avg_gain / (avg_loss + 1e-12))
    out[:period] = out[period]
    return out


def macd(
    close: Floats, fast: int = 12, slow: int = 26, signal: int = 9
) -> tuple[Floats, Floats, Floats]:
    macd_line = ema(close, fast) - ema(close, slow)
    signal_line = ema(macd_line, signal)
    return macd_line, signal_line, macd_line - signal_line


def _rolling(values: Floats, period: int) -> Floats:
    """A (n, period) view of the trailing window at each bar, edge-padded at the left.

    Edge padding rather than NaN: every pane in this codebase is `len(close)` long and rendered from
    bar 0, and the warm-up prefix is trimmed before anyone sees it anyway.
    """
    padded = np.concatenate([np.full(period - 1, values[0]), values])
    return np.lib.stride_tricks.sliding_window_view(padded, period)


def sma(values: Floats, period: int) -> Floats:
    return np.asarray(_rolling(values, period).mean(axis=1), dtype=np.float64)


def rolling_std(values: Floats, period: int) -> Floats:
    """Population standard deviation over the trailing window — what a Bollinger band is drawn from."""
    return np.asarray(_rolling(values, period).std(axis=1), dtype=np.float64)


def true_range(high: Floats, low: Floats, close: Floats) -> Floats:
    """max(high-low, |high-prev close|, |low-prev close|) — the range a gap does not hide."""
    prev = np.concatenate([close[:1], close[:-1]])
    return np.asarray(
        np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev))), dtype=np.float64
    )


def atr(high: Floats, low: Floats, close: Floats, period: int = 20) -> Floats:
    """Average true range: the *average size of a bar*, which is what makes Keltner different."""
    return sma(true_range(high, low, close), period)


def bollinger(close: Floats, period: int = 20, mult: float = 2.0) -> tuple[Floats, Floats, Floats]:
    """(basis, upper, lower) = mean ± `mult` standard DEVIATIONS of the close."""
    basis = sma(close, period)
    dev = mult * rolling_std(close, period)
    return basis, basis + dev, basis - dev


def keltner(
    high: Floats, low: Floats, close: Floats, period: int = 20, mult: float = 1.5
) -> tuple[Floats, Floats, Floats]:
    """(basis, upper, lower) = mean ± `mult` ATRs.

    Same mean, a different ruler: the ATR reacts to how far a bar TRAVELS, the standard deviation to how
    far closes SCATTER, which is why the two envelopes cross at all (m16-l1).
    """
    basis = sma(close, period)
    band = mult * atr(high, low, close, period)
    return basis, basis + band, basis - band


def squeeze_on(bb_upper: Floats, bb_lower: Floats, kc_upper: Floats, kc_lower: Floats) -> Floats:
    """1.0 where the Bollinger band sits INSIDE the Keltner channel — the compression flag."""
    inside = (bb_upper < kc_upper) & (bb_lower > kc_lower)
    return inside.astype(np.float64)


def squeeze_momentum(high: Floats, low: Floats, close: Floats, period: int = 20) -> Floats:
    """The signed histogram the squeeze indicator prints, in price units.

    Deviation of the close from the midpoint between the period's donchian mid and its mean, fitted
    with a rolling linear regression and read at the last bar — i.e. *where the deviation is heading*,
    not where it stands. Zero-centred by construction, which is the whole of its reading: sign says
    which way, magnitude says how hard. m16-l1 presents it as a packaging of the two envelopes above.
    """
    donchian = (_rolling(high, period).max(axis=1) + _rolling(low, period).min(axis=1)) / 2.0
    deviation = close - (donchian + sma(close, period)) / 2.0
    window = _rolling(deviation, period)
    x_centred = np.arange(period, dtype=np.float64) - (period - 1) / 2.0
    # The regression is `numerics`, not a `@`: a matrix product is a BLAS call, so its kernel and its
    # use of fused multiply-add are the machine's choice rather than this file's.
    row_mean, slope = rowwise_mean_and_centred_slope(window, x_centred)
    return np.asarray(row_mean + slope * x_centred[-1], dtype=np.float64)
