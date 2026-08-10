# SPDX-License-Identifier: AGPL-3.0-only
"""Volatility-cycle injector (m16-l1): compression, expansion, and the squeeze between them.

The two labels are PHASES, not outcomes: `compression` ends the window coiled, `expansion` ends it
travelling. Everything drawn — the Bollinger envelope, the Keltner envelope, the momentum pane and its
compression row — is COMPUTED from the candles rather than planted, which is what makes the chart able
to be wrong: if the shape did not really compress, the bands say so and `test_chart_volatility.py`
fails.

What makes the two envelopes cross at all is the ruler, not the volatility (m16-l1): a Bollinger band
is drawn from how far the CLOSES scatter, a Keltner channel from how far a BAR travels. So a squeeze is
manufactured the way a real one happens — a stretch where price keeps moving inside each bar while the
closes stay pinned — never by turning the volatility knob down and hoping.

Bidirectional: the drift's sign is a draw, and the labels are about band geometry, which has none.
"""

from __future__ import annotations

from typing import ClassVar

import numpy as np

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.indicators import bollinger, keltner, squeeze_momentum, squeeze_on
from tradeschool.exercises.charts.patterns.base import Annotation, PatternInjector, PatternResult
from tradeschool.exercises.charts.patterns.common import WARMUP, bounded_noise, with_warmup
from tradeschool.exercises.charts.types import Series

_BASE_PRICES = (120.0, 480.0, 1850.0, 9500.0, 27000.0)

#: The band period every drawn envelope and the pane share. One number, because the whole lesson is
#: about comparing two rulers over the SAME window — different periods would confuse the reading.
PERIOD = 20

#: Where the phase the label names begins, as a window fraction. Everything before it is the other half
#: of the cycle, so both charts show the cycle rather than a state.
_PHASE_F = 0.62
#: Per-bar close-to-close travel, before and during the phase. A compression does not merely get
#: quieter, it gets DIRECTIONLESS — see `_REVERT`.
_CALM = (0.0022, 0.0032)
#: An expansion has to look violent next to the coil and still be a chart somebody could screenshot.
#: The credibility bound is 5% on any of the last six candles; at (0.013, 0.018) the sweep printed a
#: 6.4% bar, so the live phase is drawn from here and CLIPPED at `_CLIP` sigmas.
_LIVE = (0.0100, 0.0140)
_CLIP = 2.5
#: ...and a hard ceiling on any single bar's close-to-close move, which is what actually makes the
#: bound safe: `_CLIP` alone still let an escalated retry stack its drift on top of a 2.5-sigma draw and
#: print 4.5%. 4% is a believable crypto candle and leaves the 5% bound a fifth of itself in headroom.
_MAX_STEP = 0.040
#: How hard the closes are pulled back to the middle of the coil. This, not the volatility, is what
#: puts the Bollinger band inside the Keltner channel: mean reversion collapses the SCATTER of the
#: closes while each bar still travels, which is the mechanism m16-l1 describes.
_REVERT = 0.55
#: The expansion's drift, as a per-bar fraction — a phase that goes somewhere, which is what makes the
#: closes disperse and pushes the Bollinger band back outside.
_EXPAND_DRIFT = (0.008, 0.012)
_NOISE = 0.0015
#: How much harder each retry pushes the phase, and how many are allowed. A chart whose bands
#: contradict its own label is not a hard case, it is an unanswerable question with a confident ground
#: truth, so the injector re-draws rather than shipping one — the same stance `RsiDivergenceInjector`
#: takes towards a divergence that did not land.
_ESCALATE = 0.30
_ATTEMPTS = 6


class SqueezeUnplantable(RuntimeError):
    """The requested phase did not show up in the bands for this seed, even after escalating."""


def _phase_path(
    rng: np.random.Generator, n: int, base: float, target: str, escalation: float = 0.0
) -> np.ndarray:
    """The close path, in log price: half a cycle, then the phase the label names."""
    start = int(_PHASE_F * n)
    log_p = np.empty(n)
    log_p[0] = float(np.log(base))
    sign = float(rng.choice((-1.0, 1.0)))

    # The lead-in is the OTHER half of the cycle, so a `compression` chart opens busy and an `expansion`
    # chart opens quiet — clustering, which is the first thing m16-l1 claims.
    lead_sigma = float(rng.uniform(*(_LIVE if target == "compression" else _CALM)))
    phase_sigma = float(rng.uniform(*(_CALM if target == "compression" else _LIVE)))
    drift = 0.0 if target == "compression" else sign * float(rng.uniform(*_EXPAND_DRIFT))
    if target == "compression":
        phase_sigma /= 1.0 + escalation  # quieter closes
        revert = min(0.9, _REVERT * (1.0 + escalation))  # ...pinned harder to the middle
    else:
        revert = _REVERT
        drift *= 1.0 + escalation  # further, faster: the closes have to scatter

    def step(sigma: float) -> float:
        return float(np.clip(rng.normal(0.0, sigma), -_CLIP * sigma, _CLIP * sigma))

    for i in range(1, n):
        if i < start:
            move = step(lead_sigma)
            if target == "expansion":  # the quiet lead-in is a coil too, or the cycle has one phase
                move += revert * (log_p[max(0, i - PERIOD)] - log_p[i - 1])
            log_p[i] = log_p[i - 1] + move
        elif target == "compression":
            anchor = log_p[start - 1]
            log_p[i] = log_p[i - 1] + revert * (anchor - log_p[i - 1]) + step(phase_sigma)
        else:
            log_p[i] = log_p[i - 1] + float(np.clip(drift + step(phase_sigma), -_MAX_STEP, _MAX_STEP))
    return np.asarray(np.exp(log_p), dtype=float)


def _envelopes(series: Series) -> dict[str, np.ndarray]:
    high = np.asarray(series.high, dtype=float)
    low = np.asarray(series.low, dtype=float)
    close = np.asarray(series.close, dtype=float)
    _bb, bb_up, bb_lo = bollinger(close, PERIOD)
    _kc, kc_up, kc_lo = keltner(high, low, close, PERIOD)
    return {"bb_upper": bb_up, "bb_lower": bb_lo, "kc_upper": kc_up, "kc_lower": kc_lo}


def _pane(series: Series) -> tuple[np.ndarray, np.ndarray]:
    high = np.asarray(series.high, dtype=float)
    low = np.asarray(series.low, dtype=float)
    close = np.asarray(series.close, dtype=float)
    env = _envelopes(series)
    state = squeeze_on(env["bb_upper"], env["bb_lower"], env["kc_upper"], env["kc_lower"])
    return squeeze_momentum(high, low, close, PERIOD), state


class VolatilityBandsInjector(PatternInjector):
    name: ClassVar[str] = "volatility_bands"
    labels: ClassVar[tuple[str, ...]] = ("compression", "expansion")
    #: The label IS the visible state of the bands at the right edge, so no resolution is being hidden
    #: and the ambient tail is deliberately NOT applied: it fixes the last bars' volatility, which on
    #: this chart is the answer. The credibility bound still applies and is what keeps the expansion's
    #: candles inside believable size.
    hides_resolution: ClassVar[bool] = False
    indicator: ClassVar[str] = "momentum"

    def build(self, rng: np.random.Generator, n: int, target: str) -> PatternResult:
        if target not in self.labels:  # pragma: no cover - guarded by the config validator
            raise ValueError(f"unknown volatility_bands label {target!r}")
        base = float(rng.choice(_BASE_PRICES)) * float(rng.uniform(0.9, 1.1))
        # Build, then LOOK at the bands: the envelopes are computed from the candles, so whether the
        # phase actually landed is a fact about the chart rather than about the parameters.
        for attempt in range(_ATTEMPTS):
            path = _phase_path(rng, n, base, target, escalation=_ESCALATE * attempt)
            close_visible = path * np.exp(bounded_noise(rng, n, amp=_NOISE))
            close_full = with_warmup(rng, close_visible, sigma=0.004)
            series = build_series(rng, close_full)
            momentum, state = _pane(series)
            if bool(state[-1] > 0.5) == (target == "compression"):
                break
        else:  # pragma: no cover - `test_chart_volatility.py` asserts no seed reaches this
            raise SqueezeUnplantable(f"could not plant {target!r} in the bands")
        overlays = {k: v.tolist() for k, v in _envelopes(series).items()}
        marker = WARMUP + int((_PHASE_F + (1.0 - _PHASE_F) / 2) * n)
        return PatternResult(
            close_full=close_full,
            warmup=WARMUP,
            label=target,
            annotations=[Annotation(index=marker, kind="marker", label=target)],
            overlays=overlays,
            candles_full=series,
            momentum_full=momentum,
            momentum_state_full=state,
            # Compression says expansion is coming and not which way (m16-l1's closing reading), so the
            # figure of a compression must not resolve in a direction — that would be the lesson's own
            # error drawn as a chart. An expansion is already going somewhere and simply continues.
            resolution_hint=0.0,
        )

    def figure_overlays(self, close_full: np.ndarray, series: Series) -> dict[str, list[float]]:
        """Recompute the envelopes over the EXTENDED series — see `figures._panel_payload`."""
        return {k: v.tolist() for k, v in _envelopes(series).items()}

    def figure_momentum(
        self, close_full: np.ndarray, series: Series
    ) -> tuple[np.ndarray, np.ndarray]:
        """...and the pane with them, so the squeeze row keeps reading the bars actually drawn."""
        return _pane(series)
