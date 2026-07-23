# SPDX-License-Identifier: AGPL-3.0-only
"""Indicator maths (NumPy, float — scenario data, not financial grading §8): RSI and MACD."""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

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

    Textbook Wilder: the first average gain/loss is the simple mean of the first `period` price
    changes; subsequent values use Wilder's smoothing. RSI is only defined from index `period`
    onward — earlier bars are warm-up and are filled with the first real value (callers drop them).
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
