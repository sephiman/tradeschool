# SPDX-License-Identifier: AGPL-3.0-only
"""CVD-divergence injector (module m26): cumulative volume delta read against price.

A DETECTION pattern. Price makes a second extreme of the same kind late in the window; the tell is
what the **cumulative volume delta** — the running sum of (taker buy volume - taker sell volume),
shown in the lower pane — did while price got there:

* ``cvd_bullish_divergence`` — price makes a LOWER LOW, CVD makes a HIGHER low. Sellers reached
  further and got less for it: their aggression is being absorbed by a resting buyer. This is m14's
  absorption and m09's spring test measured instead of eyeballed.
* ``cvd_bearish_divergence`` — price makes a HIGHER HIGH, CVD makes a LOWER high. The new peak was
  bought by less aggression than the last one — distribution into strength.
* ``cvd_confirms`` — CVD makes its new extreme WITH price. The aggression agrees with the move, so
  there is no divergence to read: a genuine, flow-backed break rather than an absorbed one.

Unlike m17's open interest, CVD cannot be identical across labels — a divergence is by definition a
disagreement between two series, so both have to be built. What IS held label-independent is
everything that could leak the answer another way:

* the answer lives in the CVD pane, not in price: the two divergence labels and ``cvd_confirms``
  share the same price geometry (a second extreme reached on a shallow leg, flat afterwards), so the
  candles narrow the choice to a direction's pair and only the CVD line separates that pair — which
  is exactly the drill;
* ``cvd_confirms`` is built in BOTH directions (coin-flipped), so neither divergence label owns a
  direction the confirming case cannot also show;
* the ``sign`` coin is drawn for every label, so the RNG stream does not fork and the noise draws
  that follow are identically distributed per label;
* the visible window ends in the standard drift-free ambient tail, so the resolution is off screen
  and the last candles cannot betray the label (the blocking statistical gate).

The CVD is generated, not derived from candle shape: a delta read off a candle's body would be a
restatement of price the learner could answer without the pane, and would not be order-flow data at
all. It is built as a per-bar taker-imbalance RATIO of that bar's volume — a price-tracking term plus
a piecewise leg bias — so ``|delta| <= 0.78 x volume`` holds bar by bar by construction and the pane
can never show flow the volume bars could not have carried.

Vetted over 300 seeds per label at n = 110, 120, 130 (the exercise) and 150 (the figure): no seed
failed to plant, the second price extreme always cleared its swing by >= 2.2%, and CVD's second swing
always landed >= 0.24 of the pane's own height from the first — several times the verification gate,
so no chart is technically-correct-but-unreadable.
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
    """A believable volume series for the full path: a noisy baseline (the house idiom) lifted where
    the bar moved, using the window's typical move as the yardstick so no rolling window is needed."""
    logret = np.diff(np.log(close), prepend=np.log(close[0]))
    typical = float(np.median(np.abs(logret))) or 1e-9
    move = np.clip(np.abs(logret) / typical, 0.0, 6.0)
    noise = 0.70 + 0.55 * np.abs(rng.normal(0.0, 1.0, len(close)))
    return _BASE_VOLUME * noise * (0.75 + 0.45 * move)


def _cvd(close: Floats, volume: Floats, s1: int, s2: int, bias: float) -> Floats:
    """Cumulative volume delta over the full path, anchored to 0 where the visible window opens.

    Each bar contributes `volume x ratio`, where ratio is the fraction of that bar's volume that was
    net aggressive on one side: a price-tracking term everywhere, plus `bias` between the two swings
    (the absorption / confirmation flow). Clipping the ratio is what guarantees the pane never shows
    more signed flow than the volume bar beneath it could have carried.
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
    """The rendered series must actually read as labelled at the two swings, with margins that dwarf
    the noise: price a clear new extreme, CVD clearly against it (divergence) or with it (confirms)."""
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
