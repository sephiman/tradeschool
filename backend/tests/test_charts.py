# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic candle engine, RSI, divergence injector and the two chart generators."""

from __future__ import annotations

import numpy as np
import pytest

from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.indicators import macd, rsi
from tradeschool.exercises.charts.injectors import DivergenceUnplantable, RsiDivergenceInjector
from tradeschool.exercises.charts.types import DivergenceType
from tradeschool.exercises.fixture_chart import FixtureChartGenerator
from tradeschool.exercises.synthetic_chart import SyntheticChartGenerator, _instantiate

INJECTOR = RsiDivergenceInjector()
N = 120

_REGULAR = [DivergenceType.BULLISH_REGULAR, DivergenceType.BEARISH_REGULAR]
_HIDDEN = [DivergenceType.BULLISH_HIDDEN, DivergenceType.BEARISH_HIDDEN]

# StockCharts' canonical 14-period Wilder RSI worked example (closes -> expected RSI).
_RSI_REF_CLOSES = [
    44.3389, 44.0902, 44.1497, 43.6124, 44.3278, 44.8264, 45.0955, 45.4245, 45.8433, 46.0826,
    45.8931, 46.0328, 45.6140, 46.2820, 46.2820, 46.0028, 46.0328, 46.4116, 46.2222, 45.6439,
    46.2122, 46.2521, 45.7137, 46.4515, 45.7835, 45.3548, 44.0288, 44.1783, 44.2181, 44.5672,
    43.4205, 42.6628, 43.1314,
]


def _holds(target: DivergenceType, close: np.ndarray, ind: np.ndarray, s1: int, s2: int) -> bool:
    hp, lp = close[s2] > close[s1], close[s2] < close[s1]
    hi, li = ind[s2] > ind[s1], ind[s2] < ind[s1]
    return {
        DivergenceType.BEARISH_REGULAR: hp and li,
        DivergenceType.BULLISH_REGULAR: lp and hi,
        DivergenceType.BULLISH_HIDDEN: hp and li,
        DivergenceType.BEARISH_HIDDEN: lp and hi,
    }[target]


def test_rsi_matches_wilder_reference() -> None:
    values = rsi(np.array(_RSI_REF_CLOSES, dtype=float), period=14)
    # Expected values from the published worked example (indexes are 0-based on the close series).
    assert values[14] == pytest.approx(70.53, abs=0.1)
    assert values[15] == pytest.approx(66.32, abs=0.1)
    assert values[28] == pytest.approx(41.87, abs=0.2)
    # RSI(14) near 100 is a red flag for a broken implementation; a real series stays well below.
    assert values.max() < 90.0


@pytest.mark.parametrize("target", _REGULAR + _HIDDEN)
def test_injector_plants_the_labeled_divergence(target: DivergenceType) -> None:
    # For many seeds, the planted swings must actually exhibit the labeled divergence on RSI.
    for seed in range(40):
        rng = np.random.default_rng(seed)
        close, _warmup, s1, s2 = INJECTOR.build(rng, N, target, "rsi")
        assert s1 is not None and s2 is not None
        assert _holds(target, close, rsi(close), s1, s2), f"{target} failed at seed {seed}"


def test_series_stops_shortly_after_second_swing() -> None:
    # Detection exercises must not show the resolution: the chart ends a short, ambient stretch
    # after swing2 (swing2 is never the very last candle, nor buried deep in the series).
    gen = SyntheticChartGenerator()
    config = gen.parse_config(CHART_RAW)
    for seed in range(20):
        target, _s1, s2, payload = _instantiate(config, seed)
        assert target is DivergenceType.BEARISH_REGULAR and s2 is not None
        series = payload["series"]
        visible_len = len(series["close"])  # type: ignore[index]
        tail = visible_len - 1 - s2
        assert 2 <= tail <= 18, f"seed {seed}: {tail} candles after swing2 (want a few, no resolution)"


def _last3(payload: dict) -> tuple[float, float]:
    """(net log-return of last 3 candles, mean absolute log-return of last 3 candles)."""
    close = np.asarray(payload["series"]["close"], dtype=float)
    r = np.diff(np.log(close))[-3:]
    return float(r.sum()), float(np.mean(np.abs(r)))


def _welch_t(a: np.ndarray, b: np.ndarray) -> float:
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else 0.0


def _collect_last3(targets: list[str], per: int) -> tuple[np.ndarray, np.ndarray]:
    gen = SyntheticChartGenerator()
    nets: list[float] = []
    abss: list[float] = []
    for tv in targets:
        choices = ["none", tv] if tv != "none" else ["none"]
        config = gen.parse_config(
            {"type": "synthetic_chart", "prompt": {"en": "x", "es": "x"}, "indicator": "rsi",
             "n": N, "targets": [tv], "choices": choices}
        )
        for seed in range(per):
            _t, _s1, _s2, payload = _instantiate(config, seed)
            net, ab = _last3(payload)
            nets.append(net)
            abss.append(ab)
    return np.array(nets), np.array(abss)


def test_last_candles_do_not_leak_the_label() -> None:
    """The final candles' distribution is not predictive of the label (round-6 leak)."""
    bull_net, bull_abs = _collect_last3(["bullish_regular", "bullish_hidden"], 120)
    bear_net, bear_abs = _collect_last3(["bearish_regular", "bearish_hidden"], 120)
    none_net, none_abs = _collect_last3(["none"], 240)

    # 1) Net direction of the last 3 candles must not separate bullish from bearish. (Under the old
    #    leak, bullish ended sharply up and bearish sharply down -> |t| would be enormous.)
    assert abs(_welch_t(bull_net, bear_net)) < 4.0

    # 2) No group has a systematic net drift in its final candles (mean within a few standard errors).
    for arr in (bull_net, bear_net, none_net):
        se = arr.std(ddof=1) / np.sqrt(len(arr))
        assert abs(arr.mean()) < 4.0 * se

    # 3) Magnitude of the final move must not separate `none` from the divergence charts.
    div_abs = np.concatenate([bull_abs, bear_abs])
    assert abs(_welch_t(none_abs, div_abs)) < 4.0


def test_injector_macd_never_mislabels() -> None:
    # MACD divergence is best-effort in Phase 1: the injector may decline a seed, but it must
    # NEVER return a chart whose MACD disagrees with the label.
    succeeded = 0
    for seed in range(30):
        rng = np.random.default_rng(seed)
        try:
            close, _warmup, s1, s2 = INJECTOR.build(rng, N, DivergenceType.BEARISH_REGULAR, "macd")
        except DivergenceUnplantable:
            continue
        assert s1 is not None and s2 is not None
        line, _, _ = macd(close)
        assert _holds(DivergenceType.BEARISH_REGULAR, close, line, s1, s2)
        succeeded += 1
    assert succeeded > 0  # MACD works for at least some seeds


def test_injector_is_seed_deterministic() -> None:
    a = INJECTOR.build(np.random.default_rng(3), N, DivergenceType.BULLISH_REGULAR, "rsi")[0]
    b = INJECTOR.build(np.random.default_rng(3), N, DivergenceType.BULLISH_REGULAR, "rsi")[0]
    assert np.array_equal(a, b)


def test_candles_are_coherent() -> None:
    rng = np.random.default_rng(11)
    close, _warmup, _s1, _s2 = INJECTOR.build(rng, N, DivergenceType.BEARISH_REGULAR, "rsi")
    series = build_series(rng, close)
    n = len(series.close)
    assert len(series.open) == len(series.high) == len(series.low) == len(series.volume) == n
    for i in range(n):
        assert series.high[i] >= max(series.open[i], series.close[i]) - 1e-6
        assert series.low[i] <= min(series.open[i], series.close[i]) + 1e-6
        assert series.volume[i] > 0


CHART_RAW = {
    "type": "synthetic_chart",
    "prompt": {"en": "classify", "es": "clasifica"},
    "indicator": "rsi",
    "n": N,
    "targets": ["bearish_regular"],
    "choices": ["none", "bullish_regular", "bearish_regular"],
    "explanation": {"en": "note", "es": "nota"},
}


def test_synthetic_generate_hides_solution_and_grades() -> None:
    gen = SyntheticChartGenerator()
    config = gen.parse_config(CHART_RAW)
    inst = gen.generate(config, seed=5, locale="en")
    assert "series" in inst.payload and "rsi" in inst.payload
    assert "divergence" not in inst.payload and "swing1" not in inst.payload
    # Visible window is exactly n candles (warm-up dropped).
    assert len(inst.payload["rsi"]) == N  # type: ignore[arg-type]

    # Single target -> always bearish_regular for this config.
    right = gen.grade(config, seed=5, answer={"divergence": "bearish_regular"}, locale="en")
    assert right.correct is True
    assert right.correct_answer["divergence"] == "bearish_regular"  # type: ignore[index]
    wrong = gen.grade(config, seed=5, answer={"divergence": "none"}, locale="en")
    assert wrong.correct is False


def test_none_charts_reach_rsi_extremes_without_pegging() -> None:
    # A trending stretch must push RSI to oversold/overbought somewhere across seeds — while never
    # pegging at 0/100 (the round-3 concern: RSI must not stay compressed in a mid band).
    gen = SyntheticChartGenerator()
    config = gen.parse_config(
        {"type": "synthetic_chart", "prompt": {"en": "x", "es": "x"}, "indicator": "rsi",
         "n": N, "targets": ["none"], "choices": ["none"]}
    )
    mins, maxs = [], []
    for seed in range(30):
        _t, _s1, _s2, payload = _instantiate(config, seed)
        r = np.array(payload["rsi"])
        mins.append(float(r.min()))
        maxs.append(float(r.max()))
    assert min(mins) < 30.0, "no chart reached oversold — RSI range is over-compressed"
    assert max(maxs) > 70.0, "no chart reached overbought — RSI range is over-compressed"
    assert min(mins) > 1.0 and max(maxs) < 99.0, "RSI pegged at an extreme"


@pytest.mark.parametrize("target", _REGULAR + _HIDDEN)
def test_divergence_shows_in_rendered_rsi(target: DivergenceType) -> None:
    # The rendered RSI at the two swings must actually diverge (and stay non-degenerate).
    gen = SyntheticChartGenerator()
    config = gen.parse_config(
        {"type": "synthetic_chart", "prompt": {"en": "x", "es": "x"}, "indicator": "rsi",
         "n": N, "targets": [target.value], "choices": ["none", target.value]}
    )
    for seed in range(15):
        _t, s1, s2, payload = _instantiate(config, seed)
        r = payload["rsi"]
        assert s1 is not None and s2 is not None
        assert abs(r[s1] - r[s2]) >= 2.0, f"{target} seed {seed}: RSI barely diverges"
        assert min(r) > 1.0 and max(r) < 99.0


def test_synthetic_is_deterministic() -> None:
    gen = SyntheticChartGenerator()
    config = gen.parse_config(CHART_RAW)
    first = gen.generate(config, seed=9, locale="en").payload
    assert first == gen.generate(config, seed=9, locale="en").payload


def test_fixture_generator_roundtrip() -> None:
    # Build one real (warm-up-trimmed) fixture with the engine, then serve + grade it.
    rng = np.random.default_rng(2)
    close_full, warmup, s1f, s2f = INJECTOR.build(rng, N, DivergenceType.BEARISH_REGULAR, "rsi")
    close = close_full[warmup:]
    series = build_series(rng, close_full)
    line, signal, hist = macd(close_full)
    fixture = {
        "label": "bearish_regular",
        "indicator": "rsi",
        "series": {
            "time": series.time[warmup:],
            "open": series.open[warmup:],
            "high": series.high[warmup:],
            "low": series.low[warmup:],
            "close": series.close[warmup:],
            "volume": series.volume[warmup:],
        },
        "rsi": [round(float(x), 2) for x in rsi(close_full)[warmup:]],
        "macd_line": [round(float(x), 4) for x in line[warmup:]],
        "macd_signal": [round(float(x), 4) for x in signal[warmup:]],
        "macd_hist": [round(float(x), 4) for x in hist[warmup:]],
        "swing1": (s1f - warmup) if s1f is not None else None,
        "swing2": (s2f - warmup) if s2f is not None else None,
    }
    assert len(close) == N
    gen = FixtureChartGenerator()
    config = gen.parse_config(
        {
            "type": "fixture_chart",
            "prompt": {"en": "classify", "es": "clasifica"},
            "choices": ["none", "bearish_regular"],
            "fixtures": [fixture],
        }
    )
    inst = gen.generate(config, seed=1, locale="en")
    assert "series" in inst.payload
    assert gen.grade(config, seed=1, answer={"divergence": "bearish_regular"}, locale="en").correct is True
    assert gen.grade(config, seed=1, answer={"divergence": "none"}, locale="en").correct is False
