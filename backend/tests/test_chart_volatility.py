# SPDX-License-Identifier: AGPL-3.0-only
"""The volatility family (m16): the two envelopes, the squeeze between them, and the momentum pane.

Two things are under test and they are deliberately separated. §1 is the INDICATOR MATHS, checked
against hand-built series where the right answer is known by construction rather than by generation —
without it, an envelope that is subtly wrong would simply move the injector's tuning with it. §2 is the
`volatility_bands` contract: the label names a phase, and the phase has to be visible IN THE BANDS,
which are computed from the candles and can therefore disagree with it.

§3 covers the zero-centred pane as a GENERIC framework capability rather than as m16's indicator — it
is the first pane in this codebase to carry a state row, and what that row owes the renderer is checked
here for any injector that ever ships one.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tradeschool.exercises.charts.indicators import (
    atr,
    bollinger,
    keltner,
    rolling_std,
    sma,
    squeeze_momentum,
    squeeze_on,
    true_range,
)
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.charts.patterns.volatility_bands import PERIOD
from tradeschool.exercises.figures import build_figure, load_figures
from tradeschool.exercises.pattern_chart import PatternChartConfig, PatternChartGenerator, _full

_SEEDS = 250
_N = 130
_CONTENT = Path(__file__).resolve().parents[2] / "content"
#: Named as well as discovered — see the same note in `test_chart_bands.py`.
_PANE_INJECTORS = {"volatility_bands"}

Payload = dict[str, object]


def _config(injector: str, targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": n, "targets": targets, "choices": list(get_injector(injector).labels)}
    )


# --- 1. the maths, against series whose answer is known by construction ---------------------------


def test_sma_and_rolling_std_are_left_padded_not_truncated() -> None:
    """Every pane in this codebase is `len(close)` long and drawn from bar 0 — no NaN prologue."""
    values = np.arange(10, dtype=float)
    assert len(sma(values, 4)) == len(values) and len(rolling_std(values, 4)) == len(values)
    assert sma(values, 4)[0] == 0.0, "the left edge is the first value repeated, not a partial mean"
    assert sma(values, 4)[-1] == pytest.approx(7.5)  # mean(6,7,8,9)


def test_true_range_sees_a_gap_that_high_minus_low_misses() -> None:
    """The whole reason a Keltner is not drawn from the bar's own range."""
    high = np.array([100.0, 120.0])
    low = np.array([98.0, 118.0])
    close = np.array([99.0, 119.0])
    assert true_range(high, low, close)[1] == pytest.approx(21.0)  # 120 - 99, not 120 - 118


def test_bollinger_is_drawn_from_scatter_and_keltner_from_travel() -> None:
    """m16-l1's claim, made false-able: a series with tight closes and wide bars puts BB inside KC.

    Same closes, same mean; only the bars' RANGE differs between the two constructions, and only the
    Keltner moves. If this ever stops holding, the lesson's core distinction has gone with it.
    """
    close = np.linspace(100.0, 130.0, 60)  # closes that scatter steadily — a wide Bollinger
    narrow_high, narrow_low = close.copy(), close.copy()  # ...printed by bars with no range at all
    wide_high, wide_low = close + 4.0, close - 4.0  # ...and by bars that travel

    _b, bb_up, bb_lo = bollinger(close, PERIOD)
    _n, narrow_up, narrow_lo = keltner(narrow_high, narrow_low, close, PERIOD)
    _w, wide_up, wide_lo = keltner(wide_high, wide_low, close, PERIOD)

    assert not bool(squeeze_on(bb_up, bb_lo, narrow_up, narrow_lo)[-1]), "narrow bars: no squeeze"
    assert bool(squeeze_on(bb_up, bb_lo, wide_up, wide_lo)[-1]), "wide bars, same closes: squeezed"
    assert atr(wide_high, wide_low, close, PERIOD)[-1] > atr(narrow_high, narrow_low, close, PERIOD)[-1]


def test_squeeze_momentum_is_zero_centred_and_signed_by_direction() -> None:
    """Sign says which way, magnitude says how hard — and a flat market says nothing."""
    flat = np.full(80, 100.0)
    assert abs(float(squeeze_momentum(flat, flat, flat, PERIOD)[-1])) < 1e-9

    up = np.linspace(100.0, 130.0, 80)
    down = up[::-1].copy()
    assert float(squeeze_momentum(up, up, up, PERIOD)[-1]) > 0
    assert float(squeeze_momentum(down, down, down, PERIOD)[-1]) < 0


# --- 2. the `volatility_bands` contract: the phase is visible in the bands ------------------------


def _pane_of(f: object) -> tuple[np.ndarray, np.ndarray]:
    w = f.warmup  # type: ignore[attr-defined]
    return (
        np.asarray(f.momentum[w:], dtype=float),  # type: ignore[attr-defined]
        np.asarray(f.momentum_state[w:], dtype=float),  # type: ignore[attr-defined]
    )


def _envelope(f: object) -> dict[str, np.ndarray]:
    w = f.warmup  # type: ignore[attr-defined]
    return {k: np.asarray(v[w:], dtype=float) for k, v in f.overlays.items()}  # type: ignore[attr-defined]


@pytest.mark.parametrize(("label", "squeezed"), [("compression", True), ("expansion", False)])
def test_the_phase_the_label_names_is_the_phase_the_bands_show(label: str, squeezed: bool) -> None:
    """The label is only true if the ENVELOPES say so — they are computed, so they can disagree."""
    config = _config("volatility_bands", [label])
    for seed in range(_SEEDS):
        _momentum, state = _pane_of(_full(config, seed))
        assert bool(state[-1] > 0.5) is squeezed, (
            f"seed {seed}: {label} ends with the squeeze "
            f"{'off' if squeezed else 'on'} — the chart contradicts its own answer"
        )
        held = float(state[-15:].mean())
        assert (held > 0.75) is squeezed, (
            f"seed {seed}: {label} holds the squeeze for {held:.0%} of the closing bars — a phase is a "
            f"stretch, not the last candle"
        )


def test_no_seed_ever_needs_the_unplantable_escape() -> None:
    """The retry ladder exists so a chart never contradicts its label; it must never run out."""
    for label in ("compression", "expansion"):
        config = _config("volatility_bands", [label])
        for seed in range(_SEEDS):
            _full(config, seed)  # raises SqueezeUnplantable if the ladder is exhausted


@pytest.mark.parametrize(("label", "widens"), [("compression", False), ("expansion", True)])
def test_the_band_width_moves_the_way_the_cycle_says(label: str, widens: bool) -> None:
    """Volatility clusters (m16-l1): each chart opens in the OTHER phase, so the width has to travel."""
    config = _config("volatility_bands", [label])
    ratios = []
    for seed in range(_SEEDS):
        env = _envelope(_full(config, seed))
        width = env["bb_upper"] - env["bb_lower"]
        ratios.append(float(np.mean(width[-10:]) / np.mean(width[:40])))
    mean = float(np.mean(ratios))
    assert (mean > 3.0) is widens, f"{label}: the band ends {mean:.2f}x its opening width"


@pytest.mark.parametrize("label", ["compression", "expansion"])
def test_the_two_envelopes_are_published_whole_and_the_right_way_up(label: str) -> None:
    """Four lines, upper above lower, all the length of the series — or the chart draws nonsense."""
    config = _config("volatility_bands", [label])
    for seed in range(60):
        f = _full(config, seed)
        env = _envelope(f)
        assert set(env) == {"bb_upper", "bb_lower", "kc_upper", "kc_lower"}
        n = len(f.series.close) - f.warmup
        for name, values in env.items():
            assert len(values) == n, f"seed {seed}: {name} is {len(values)} long, not {n}"
            assert np.isfinite(values).all(), f"seed {seed}: {name} has a hole in it"
        assert (env["bb_upper"] > env["bb_lower"]).all()
        assert (env["kc_upper"] > env["kc_lower"]).all()


# --- 3. the zero-centred pane, as a framework capability ------------------------------------------


def test_the_pane_is_a_generic_capability_and_not_one_figure_s_indicator() -> None:
    """Any injector may declare it; the ones that do not keep exactly the payload they had."""
    assert {inj.name for inj in all_injectors() if inj.indicator == "momentum"} == _PANE_INJECTORS
    gen = PatternChartGenerator()
    from tradeschool.exercises.pattern_chart import _instantiate

    for inj in all_injectors():
        config = _config(inj.name, [inj.labels[0]])
        _lbl, _ann, payload = _instantiate(config, 0)
        has_pane = inj.indicator == "momentum"
        assert ("momentum" in payload) is has_pane, f"{inj.name}: stray momentum key"
        assert ("momentum_state" in payload) is has_pane
        assert gen  # the generator is the only path these keys travel


@pytest.mark.parametrize("label", ["compression", "expansion"])
def test_the_state_row_is_a_flag_and_the_histogram_straddles_zero(label: str) -> None:
    """What the renderer is owed: a 0/1 row it can draw as dots, and a signed series read against 0."""
    config = _config("volatility_bands", [label])
    for seed in range(60):
        momentum, state = _pane_of(_full(config, seed))
        assert set(np.unique(state)) <= {0.0, 1.0}, f"seed {seed}: the state row is not a flag"
        assert len(momentum) == len(state)
        assert momentum.min() < 0 < momentum.max(), (
            f"seed {seed}: the histogram never crosses zero — a zero-centred pane with one sign is a "
            f"pane drawn against the wrong baseline"
        )


# --- 4. the figure recomputes both over the extended series ---------------------------------------


def _panels(figure_id: str) -> list[Payload]:
    data = build_figure(load_figures(_CONTENT)[figure_id], "en")
    panels = data["panels"]
    assert isinstance(panels, list)
    return panels


def _pane_figure_panels() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for fid, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        out += [(fid, i) for i, p in enumerate(_panels(fid)) if "momentum" in p]
    return out


@pytest.mark.parametrize(("figure_id", "panel"), _pane_figure_panels())
def test_a_figure_recomputes_the_envelopes_over_its_own_resolution(figure_id: str, panel: int) -> None:
    """The bands and the pane run to the right edge, not to where the exercise window stopped.

    Continuing them with a synthetic leg — what OI and CVD get — would be meaningless here: both are
    functions of the price, so a figure recomputes them instead (`figures._panel_payload`).
    """
    p = _panels(figure_id)[panel]
    s = p["series"]
    assert isinstance(s, dict)
    n = len(s["close"])
    overlays = p["overlays"]
    assert isinstance(overlays, dict)
    for name, values in overlays.items():
        assert len(values) == n, f"{figure_id} panel{panel}: {name} stops {n - len(values)} bars short"
    for key in ("momentum", "momentum_state"):
        assert len(p[key]) == n, f"{figure_id} panel{panel}: {key} stops short of the right edge"


def test_every_injector_that_drives_the_pane_is_covered() -> None:
    """Fails if the parametrised suites' discovery silently finds nothing.

    Two different things are counted, and the difference is deliberate. A panel CARRIES the pane series
    whenever its injector supplies one — m16's bands figure does, even though it draws no pane — which is
    what the recompute test above sweeps. A panel that DECLARES `indicator: momentum` is the one that
    actually renders it, and at least one figure has to, or the render path has no coverage at all.
    """
    carried = _pane_figure_panels()
    assert carried, "no figure carries the momentum pane — it lost its figure coverage"
    declared = [
        (fid, i) for fid, i in carried if _panels(fid)[i]["indicator"] == "momentum"
    ]
    assert declared, "no figure DRAWS the momentum pane — the pane renderer is untested"
