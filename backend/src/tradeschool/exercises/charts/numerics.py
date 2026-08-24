# SPDX-License-Identifier: AGPL-3.0-only
"""Order-fixed float primitives: the same bits on every CPU, for the Kotlin port to copy.

Replaces the two BLAS entry points the generation path used to have (`np.polyfit`'s LAPACK `lstsq`,
`squeeze_momentum`'s `@`), whose kernels OpenBLAS picks from the CPU's feature bits at load time.

THE ORDER CONTRACT, which the port must reproduce exactly. Every reduction here accumulates
left to right into one accumulator starting at `+0.0`:

    var total = 0.0
    for (i in 0 until n) total += term(i)

No pairwise regrouping (what `np.sum` does, in a SIMD-dependent block size), no compensated
summation, no fused multiply-add. Python's own `sum()` is disqualified: since 3.12 it applies Neumaier
compensation to floats, so it returns a better answer than this contract allows.

NOT pinned yet: `ndarray.mean`/`std`, `np.cumsum`, `np.convolve`, `np.interp`, `np.median` elsewhere
in the path. `scripts/verify_golden_stability.py` is what says whether they matter; decide that before
adding a third reduction here.
"""

from __future__ import annotations

import numpy as np
from numpy.typing import NDArray

Floats = NDArray[np.float64]


# These three ARE the contract in executable form: `rowwise_mean_and_centred_slope` inlines the same
# loops and is asserted equal to them, so they are the spec, not spare parts.


def sum_left_to_right(values: Floats) -> float:
    """Σ values, accumulated from `+0.0` in index order."""
    total = 0.0
    for value in np.asarray(values, dtype=np.float64).tolist():
        total += value
    return total


def mean_left_to_right(values: Floats) -> float:
    """`sum_left_to_right(values) / len(values)`, as one division at the end (not a running mean)."""
    arr = np.asarray(values, dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return sum_left_to_right(arr) / float(arr.size)


def dot_left_to_right(a: Floats, b: Floats) -> float:
    """Σ a[i]·b[i] in index order: each product is rounded before it is added, never fused."""
    left = np.asarray(a, dtype=np.float64).ravel().tolist()
    right = np.asarray(b, dtype=np.float64).ravel().tolist()
    if len(left) != len(right):
        raise ValueError(f"dot_left_to_right needs equal lengths, got {len(left)} and {len(right)}")
    total = 0.0
    for u, v in zip(left, right, strict=True):
        total += u * v
    return total


def ols_slope_intercept(x: Floats, w: Floats) -> tuple[float, float]:
    """Least-squares line through (x, w), closed form. Replaces `np.polyfit(x, w, 1)`.

        slope = Σ (xᵢ−x̄)(wᵢ−w̄) / Σ (xᵢ−x̄)(xᵢ−x̄)      intercept = w̄ − slope·x̄

    One left-to-right pass with both sums advancing together; the two divisions happen at the end.
    Degenerate input (every x identical) gives slope `0.0`, so `detrend_linear` centres on w̄.
    """
    xs = np.asarray(x, dtype=np.float64).ravel().tolist()
    ws = np.asarray(w, dtype=np.float64).ravel().tolist()
    if len(xs) != len(ws):
        raise ValueError(f"ols_slope_intercept needs equal lengths, got {len(xs)} and {len(ws)}")
    n = len(xs)
    if n == 0:
        return 0.0, 0.0

    x_bar = mean_left_to_right(np.asarray(xs, dtype=np.float64))
    w_bar = mean_left_to_right(np.asarray(ws, dtype=np.float64))

    numerator = 0.0
    denominator = 0.0
    for i in range(n):
        dx = xs[i] - x_bar
        numerator += dx * (ws[i] - w_bar)
        denominator += dx * dx

    slope = numerator / denominator if denominator != 0.0 else 0.0
    return slope, w_bar - slope * x_bar


def detrend_linear(x: Floats, w: Floats) -> Floats:
    """`w` with its net linear drift removed — exactly what `polyval(polyfit(x, w, 1), x)` subtracted."""
    xs = np.asarray(x, dtype=np.float64)
    ws = np.asarray(w, dtype=np.float64)
    slope, intercept = ols_slope_intercept(xs, ws)
    return np.asarray(ws - (slope * xs + intercept), dtype=np.float64)


def rowwise_mean_and_centred_slope(window: Floats, x_centred: Floats) -> tuple[Floats, Floats]:
    """Each row's mean and its slope against the zero-centred `x_centred`, in one pass per row.

    Replaces `squeeze_momentum`'s `window.mean(axis=1)` and its `@`. The row-mean subtraction is a
    no-op in exact arithmetic (`x_centred` sums to zero) but not in floating point, so it stays.
    """
    rows = np.asarray(window, dtype=np.float64).tolist()
    xs = np.asarray(x_centred, dtype=np.float64).ravel().tolist()
    period = len(xs)
    denominator = 0.0
    for value in xs:
        denominator += value * value
    means = np.empty(len(rows), dtype=np.float64)
    slopes = np.empty(len(rows), dtype=np.float64)
    for i, row in enumerate(rows):
        total = 0.0
        for value in row:
            total += value
        row_mean = total / float(len(row))
        numerator = 0.0
        for j in range(period):
            numerator += (row[j] - row_mean) * xs[j]
        means[i] = row_mean
        slopes[i] = numerator / denominator if denominator != 0.0 else 0.0
    return means, slopes
