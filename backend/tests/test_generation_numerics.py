# SPDX-License-Identifier: AGPL-3.0-only
"""The generation path's arithmetic is fully specified: no BLAS, no `@`, a fixed summation order.

Phase W1. Pins the primitives, guards against a `np.polyfit` or a `@` returning, and records what the
switch moved — which was almost nothing visible, because every published number is rounded first.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.charts import numerics
from tradeschool.exercises.charts.indicators import squeeze_momentum
from tradeschool.exercises.charts.patterns.registry import get_injector
from tradeschool.exercises.figures import FigurePanel, FigureSpec, build_figure, load_figures
from tradeschool.exercises.pattern_chart import PatternChartGenerator
from tradeschool.exercises.pattern_chart import _instantiate as pattern_instantiate

# The generation path as a file list; both guards below walk it, so a new chart module is covered only
# if it lands under this directory.
_CHARTS_DIR = Path(numerics.__file__).parent
_GENERATION_FILES = sorted(_CHARTS_DIR.rglob("*.py"))


def test_ols_matches_the_closed_form_written_out_by_hand() -> None:
    """The primitive is the formula in its docstring, not a re-derivation of it."""
    x = np.arange(9, dtype=np.float64)
    w = np.array([0.4, -1.2, 0.9, 2.5, -0.3, 1.1, 3.0, -0.8, 1.7])

    # Explicit loops, not `sum()`: CPython's builtin uses Neumaier compensated summation on floats,
    # which is exactly the kind of "helpful" regrouping the primitive is specified NOT to do.
    x_total = 0.0
    for value in x.tolist():
        x_total += value
    w_total = 0.0
    for value in w.tolist():
        w_total += value
    x_bar = x_total / 9.0
    w_bar = w_total / 9.0
    num = 0.0
    den = 0.0
    for xi, wi in zip(x.tolist(), w.tolist(), strict=True):
        num += (xi - x_bar) * (wi - w_bar)
        den += (xi - x_bar) * (xi - x_bar)
    expected_slope = num / den
    expected_intercept = w_bar - expected_slope * x_bar

    slope, intercept = numerics.ols_slope_intercept(x, w)
    assert slope == expected_slope
    assert intercept == expected_intercept


def test_ols_is_deliberately_not_polyfit() -> None:
    """The closed form and LAPACK disagree — the premise the notes in this file rest on."""
    rng = np.random.default_rng(7)
    walk = np.cumsum(rng.normal(0.0, 0.007, 130))
    x = np.arange(130, dtype=np.float64)

    closed = numerics.ols_slope_intercept(x, walk)
    lapack = np.polyfit(x, walk, 1)

    assert (closed[0], closed[1]) != (float(lapack[0]), float(lapack[1])), (
        "polyfit and the closed form now agree bit-for-bit on this seed — re-read the recapture note "
        "in test_golden_exercise_mode.py before touching anything"
    )
    assert closed[0] == pytest.approx(float(lapack[0]), rel=1e-12)
    assert closed[1] == pytest.approx(float(lapack[1]), rel=1e-9, abs=1e-15)


def test_detrended_series_has_no_linear_drift_left() -> None:
    """Whatever the summation order, the point of detrending survives: refit and the slope is ~0."""
    rng = np.random.default_rng(11)
    walk = np.cumsum(rng.normal(0.0, 0.007, 160))
    x = np.arange(160, dtype=np.float64)

    residual = numerics.detrend_linear(x, walk)
    slope, _ = numerics.ols_slope_intercept(x, residual)
    assert abs(slope) < 1e-15


def test_fixed_order_dot_is_a_plain_multiply_add_chain() -> None:
    """No pairwise regrouping and no fused multiply-add — the two things a Kotlin `+=` cannot do."""
    a = np.array([1e16, 1.0, -1e16, 1.0])
    b = np.ones(4)
    # Left to right this is (1e16 + 1) - 1e16 + 1 == 1.0: the +1 is lost to rounding, and losing it
    # is the specified behaviour. Any implementation that "helpfully" recovers it has regrouped.
    assert numerics.dot_left_to_right(a, b) == 1.0

    rng = np.random.default_rng(3)
    u, v = rng.normal(size=64), rng.normal(size=64)
    by_hand = 0.0
    for ui, vi in zip(u.tolist(), v.tolist(), strict=True):
        by_hand += ui * vi
    assert numerics.dot_left_to_right(u, v) == by_hand


def test_rolling_regression_is_the_two_primitives_spelled_out() -> None:
    """The inlined loops must be bit-identical to calling the primitives per row."""
    rng = np.random.default_rng(4)
    x_centred = np.arange(20, dtype=np.float64) - 9.5

    for _ in range(8):
        deviation = np.cumsum(rng.normal(0.0, 0.5, 220))
        window = np.lib.stride_tricks.sliding_window_view(
            np.concatenate([np.full(19, deviation[0]), deviation]), 20
        )
        means, slopes = numerics.rowwise_mean_and_centred_slope(window, x_centred)

        denominator = 0.0
        for value in x_centred.tolist():
            denominator += value * value
        for i in range(window.shape[0]):
            row = window[i]
            row_mean = numerics.mean_left_to_right(row)
            assert means[i] == row_mean
            assert slopes[i] == numerics.dot_left_to_right(row - row_mean, x_centred) / denominator


def test_squeeze_momentum_is_still_zero_centred_and_reads_as_a_slope() -> None:
    """The `@` is gone; the indicator it computed is not (m16-l1's whole reading is sign + size)."""
    rng = np.random.default_rng(5)
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, 120)))
    high, low = close * 1.004, close * 0.996

    momentum = squeeze_momentum(high, low, close)
    assert momentum.shape == close.shape
    assert momentum.dtype == np.float64
    assert np.isfinite(momentum).all()
    # A steadily rising close must end with a positive reading: the deviation is heading up.
    rising = np.linspace(100.0, 130.0, 120)
    assert squeeze_momentum(rising * 1.004, rising * 0.996, rising)[-1] > 0.0


# --- the durable guards --------------------------------------------------------------------------


def test_no_polyfit_or_lstsq_in_the_generation_path() -> None:
    """A BLAS-backed fit in here breaks the port's bit-parity."""
    banned = {"polyfit", "polyval", "lstsq", "solve", "inv", "svd", "pinv", "eig"}
    offenders: list[str] = []
    for path in _GENERATION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in banned:
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
    assert not offenders, (
        "these go through LAPACK/OpenBLAS, whose kernel is chosen per CPU at load time — use "
        f"charts/numerics.py instead: {offenders}"
    )


def test_no_matrix_product_in_the_generation_path() -> None:
    """`@` is a BLAS call and may fuse multiply-add; `dot_left_to_right` may not."""
    offenders: list[str] = []
    for path in _GENERATION_FILES:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.BinOp) and isinstance(node.op, ast.MatMult):
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.AugAssign) and isinstance(node.op, ast.MatMult):
                offenders.append(f"{path.name}:{node.lineno}")
            if isinstance(node, ast.Attribute) and node.attr in {"dot", "matmul", "einsum", "inner"}:
                offenders.append(f"{path.name}:{node.lineno} .{node.attr}")
    assert not offenders, (
        f"matrix products are BLAS and are not bit-portable — use numerics.dot_left_to_right: {offenders}"
    )


# --- what the switch did and did not move --------------------------------------------------------
#
# EXERCISE MODE: nothing moved. These three were captured BEFORE the switch and are unchanged after
# it, as are all 84 in `test_golden_exercise_mode.py`. The raw floats DO move — 85% of detrended
# values, up to 3e-11 relative — but that is ~3e-8 on a four-figure price, a millionth of the
# half-cent a 2-decimal rounding turns on. `fakeout` stands for the 19 injectors that reach the fit;
# `volatility_bands` is the only one driving `squeeze_momentum`; `imbalance` also pins that a withheld
# `Band` stayed withheld.
_PINNED_EXERCISE = {
    "fakeout:0": "043db700deeda2ad",
    "volatility_bands:0": "552e7bfc04ca55c7",
    "imbalance:2": "d92f571868493d78",
}

# FIGURE MODE: three payloads moved, each by ONE `momentum` value, by one 0.0001 quantum — a reading
# that sat on a 4-decimal boundary and tipped. Everything else in all three is byte-identical. No
# committed golden covered them, which is why they are pinned here now.
_PINNED_FIGURE = {
    "volatility_bands:compression:2": "e364b51fdf984832",
    "volatility_bands:expansion:4": "f6fea5ab05de3423",
}

#: The shipped m16 figure, which moved by the same quantum. Separate because this one is CONTENT:
#: its seed is frozen in `content/figures/fig-m16-squeeze.yaml` and a reader sees this exact chart.
_PINNED_CONTENT_FIGURE = ("fig-m16-squeeze", "33c404af5a904335")


#: All six under one namespaced key each — the form `scripts/verify_golden_stability.py` imports so
#: its exit code certifies these alongside the 84.
PINNED: dict[str, str] = {
    **{f"exercise:{k}": v for k, v in _PINNED_EXERCISE.items()},
    **{f"figure:{k}": v for k, v in _PINNED_FIGURE.items()},
    f"content:{_PINNED_CONTENT_FIGURE[0]}": _PINNED_CONTENT_FIGURE[1],
}


def current_pins() -> dict[str, str]:
    """Recompute all six pins — the one place that knows how each is built."""
    from test_golden_exercise_mode import _fp  # the one definition of a fingerprint

    out: dict[str, str] = {}

    for key in _PINNED_EXERCISE:
        name, seed = key.rsplit(":", 1)
        labels = list(get_injector(name).labels)
        cfg = PatternChartGenerator().parse_config(
            {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": name,
             "n": 130, "targets": labels, "choices": labels}
        )
        label, ann, payload = pattern_instantiate(cfg, int(seed))
        out[f"exercise:{key}"] = _fp({"p": payload, "label": label, "ann": ann})

    for key in _PINNED_FIGURE:
        injector, target, seed = key.split(":")
        spec = FigureSpec(
            id=f"fig-{key.replace(':', '-')}",
            caption=LocalizedText(en="x", es="x"),
            panels=[
                FigurePanel(
                    generator="pattern_chart", injector=injector, target=target, seed=int(seed)
                )
            ],
        )
        out[f"figure:{key}"] = _fp(build_figure(spec, "en")["panels"])

    figure_id = _PINNED_CONTENT_FIGURE[0]
    spec = load_figures(Path(__file__).resolve().parents[2] / "content")[figure_id]
    out[f"content:{figure_id}"] = _fp(build_figure(spec, "en")["panels"])
    return out


def test_pinned_fingerprints_are_unchanged() -> None:
    current = current_pins()
    assert set(current) == set(PINNED), "the set of pins changed — one was added or removed?"
    mismatches = {k: (PINNED[k], current[k]) for k in PINNED if current[k] != PINNED[k]}
    assert not mismatches, (
        "a pinned fingerprint moved. These are not adapted to make a test pass: read the notes above, "
        f"then find out what changed and why. {mismatches}"
    )
