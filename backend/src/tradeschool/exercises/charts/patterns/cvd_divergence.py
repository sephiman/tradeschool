# SPDX-License-Identifier: AGPL-3.0-only
"""CVD-divergence injector (m26): cumulative volume delta read against price.

A DETECTION pattern. Every label shares the same price geometry, so only the CVD pane separates them —
which is the drill. Two anti-leak details that are easy to undo: ``cvd_confirms`` is built in BOTH
directions, so no divergence label owns a direction; and the ``sign`` coin is drawn for every label so
the RNG stream does not fork and the noise draws stay identically distributed.

The CVD is generated, not derived from candle shape — a delta read off a body would just restate price.
It is a per-bar taker-imbalance ratio of that bar's volume, so ``|delta| <= 0.78 x volume`` holds by
construction and the pane can never show flow the volume bars could not have carried.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np
from numpy.typing import NDArray

from tradeschool.exercises.charts.patterns.base import (
    Annotation,
    PatternInjector,
    PatternResult,
)
from tradeschool.exercises.charts.patterns.common import (
    WARMUP,
    apply_ambient_tail,
    bounded_noise,
    resolve_swing,
    shape_from_points,
    with_warmup,
)

Floats = NDArray[np.float64]

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)
_BASE_VOLUME = 1000.0

# Price profile in |log-offset|, signed at build time. Lifted from the proven m12 divergence shape:
# two same-kind extremes (0.46 and 0.90), the second a clear new extreme reached on a SHALLOWER leg,
# minor pullbacks inside each leg so no run is monotonic, and dead flat after the second swing so the
# candles that follow carry no confirmation move.
_PROFILE: tuple[tuple[float, float], ...] = (
    (0.00, 0.000), (0.15, 0.010), (0.25, 0.030), (0.34, 0.090), (0.42, 0.150), (0.46, 0.170),
    (0.54, 0.120), (0.62, 0.140), (0.70, 0.155), (0.78, 0.175), (0.86, 0.195), (0.90, 0.205),
    (1.00, 0.205),
)
_F1, _F2 = 0.46, 0.90  # window-fractions of the two swings

# Per-bar taker imbalance. `_TRACK` scales a bar's own move (as a multiple of the window's typical
# move) into the fraction of its volume that was aggressive on that side, so CVD tracks price the way
# a real one does; `_TRACK_CLIP` keeps even a violent bar short of one-sided.
_TRACK = 0.18
_TRACK_CLIP = 0.45
# Leg-2 bias: the sustained one-sided flow that either fights price (a divergence) or backs it
# (confirmation). Applied between the two swings, where price barely travels, so it — not the
# price-tracking term — decides where CVD's second swing lands.
_BIAS_DIVERGE = 0.20
_BIAS_CONFIRM = 0.13
_RATIO_CLIP = 0.78  # |delta| never exceeds this fraction of the bar's volume

_PRICE_MARGIN = 0.004  # swings must differ by at least this fraction of price to read clearly
_CVD_MARGIN = 0.08  # ...and by this fraction of the visible CVD range


class CvdUnplantable(RuntimeError):
    """The requested CVD relationship could not be realized for this seed."""


def _volume(rng: np.random.Generator, close: Floats) -> Floats:
    """A believable volume series: a noisy baseline lifted where the bar moved."""
    logret = np.diff(np.log(close), prepend=np.log(close[0]))
    typical = float(np.median(np.abs(logret))) or 1e-9
    move = np.clip(np.abs(logret) / typical, 0.0, 6.0)
    noise = 0.70 + 0.55 * np.abs(rng.normal(0.0, 1.0, len(close)))
    return _BASE_VOLUME * noise * (0.75 + 0.45 * move)


def _cvd(close: Floats, volume: Floats, s1: int, s2: int, bias: float) -> Floats:
    """Cumulative volume delta, anchored to 0 where the visible window opens.

    Clipping the per-bar ratio is what keeps the pane from showing more flow than its volume bar could.
    """
    logret = np.diff(np.log(close), prepend=np.log(close[0]))
    typical = float(np.median(np.abs(logret))) or 1e-9
    ratio = np.clip(_TRACK * logret / typical, -_TRACK_CLIP, _TRACK_CLIP)
    ratio[s1 + 1 : s2 + 1] += bias
    delta = volume * np.clip(ratio, -_RATIO_CLIP, _RATIO_CLIP)
    cvd: Floats = np.cumsum(delta)
    return cvd - float(cvd[WARMUP])


class CvdDivergenceInjector(PatternInjector):
    name: ClassVar[str] = "cvd_divergence"
    labels: ClassVar[tuple[str, ...]] = (
        "cvd_bullish_divergence",
        "cvd_bearish_divergence",
        "cvd_confirms",
    )
    hides_resolution: ClassVar[bool] = True
    indicator: ClassVar[str] = "cvd"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        # Drawn for EVERY label so the stream never forks; only `cvd_confirms` actually uses it.
        coin = 1.0 if rng.random() < 0.5 else -1.0
        if target == "cvd_bullish_divergence":
            sign = -1.0  # absorption of selling lives at a low
        elif target == "cvd_bearish_divergence":
            sign = 1.0  # distribution into strength lives at a high
        elif target == "cvd_confirms":
            sign = coin  # either direction, so price never implies "confirms"
        else:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown cvd label {target!r}")

        kind = "low" if sign < 0 else "high"
        # A divergence's leg-2 flow runs AGAINST price; a confirmation's runs with it.
        bias = (-sign * _BIAS_DIVERGE) if target != "cvd_confirms" else (sign * _BIAS_CONFIRM)
        shape = shape_from_points([(f, sign * y) for f, y in _PROFILE], n)
        i1, i2 = int(_F1 * n), int(_F2 * n)

        def attempt(amp: float) -> tuple[Floats, Floats, Floats, int, int] | None:
            close_visible = base * np.exp(shape + bounded_noise(rng, n, amp=amp)) if amp > 0 else (
                base * np.exp(shape)
            )
            apply_ambient_tail(rng, close_visible)
            close_full = with_warmup(rng, close_visible)
            s1 = WARMUP + resolve_swing(close_visible, i1, kind)
            s2 = WARMUP + resolve_swing(close_visible, i2, kind)
            if s1 == s2:
                return None
            volume = _volume(rng, close_full)
            cvd = _cvd(close_full, volume, s1, s2, bias)
            if not _verified(target, sign, close_full, cvd, s1, s2):
                return None
            return close_full, volume, cvd, s1, s2

        for k in range(7):
            built = attempt(0.010 * (0.6**k))
            if built is not None:
                break
        else:
            # Last resort: the pure shape, which encodes the price geometry by construction and is
            # already wavy enough to read. Still verified — a mislabelled chart is never returned.
            built = attempt(0.0)
            if built is None:
                raise CvdUnplantable(f"could not plant {target!r} at n={n}")

        close_full, volume, cvd, s1, s2 = built
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[
                Annotation(index=s1, kind=kind, label="1"),
                Annotation(index=s2, kind=kind, label="2"),
            ],
            volume_full=volume,
            cvd_full=cvd,
        )


def _verified(target: str, sign: float, close: Floats, cvd: Floats, s1: int, s2: int) -> bool:
    """Whether the rendered series actually reads as labelled at the two swings."""
    price_margin = _PRICE_MARGIN * float(close[s1])
    visible = cvd[WARMUP:]
    cvd_margin = _CVD_MARGIN * float(np.max(visible) - np.min(visible))
    if cvd_margin <= 0:
        return False
    price_step = float(close[s2] - close[s1])
    cvd_step = float(cvd[s2] - cvd[s1])
    # A new extreme in the shape's own direction: lower low when sign < 0, higher high when sign > 0.
    if sign * price_step <= price_margin:
        return False
    want = -sign if target != "cvd_confirms" else sign
    return want * cvd_step > cvd_margin
