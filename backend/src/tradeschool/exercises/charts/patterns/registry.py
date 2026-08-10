# SPDX-License-Identifier: AGPL-3.0-only
"""Pattern-injector registry (§3.2): one injector per `name`, never a change to the frozen generators."""

from __future__ import annotations

from tradeschool.exercises.charts.patterns.base import PatternInjector
from tradeschool.exercises.charts.patterns.candle_reaction import CandleReactionInjector
from tradeschool.exercises.charts.patterns.converging_lines import ConvergingLinesInjector
from tradeschool.exercises.charts.patterns.cvd_divergence import CvdDivergenceInjector
from tradeschool.exercises.charts.patterns.derivatives import DerivativesInjector
from tradeschool.exercises.charts.patterns.fakeout import FakeoutInjector
from tradeschool.exercises.charts.patterns.fibonacci import FibonacciInjector
from tradeschool.exercises.charts.patterns.imbalance import ImbalanceInjector
from tradeschool.exercises.charts.patterns.liquidity_sweep import LiquiditySweepInjector
from tradeschool.exercises.charts.patterns.ma_context import MaContextInjector
from tradeschool.exercises.charts.patterns.macd_cross import MacdCrossInjector
from tradeschool.exercises.charts.patterns.market_structure import MarketStructureInjector
from tradeschool.exercises.charts.patterns.multi_timeframe import MultiTimeframeInjector
from tradeschool.exercises.charts.patterns.origin_zone import OriginZoneInjector
from tradeschool.exercises.charts.patterns.oscillator_reading import OscillatorReadingInjector
from tradeschool.exercises.charts.patterns.stop_limit_gap import StopLimitGapInjector
from tradeschool.exercises.charts.patterns.trade_anatomy import TradeAnatomyInjector
from tradeschool.exercises.charts.patterns.trend_channel import TrendChannelInjector
from tradeschool.exercises.charts.patterns.volatility_bands import VolatilityBandsInjector
from tradeschool.exercises.charts.patterns.volume_confirmation import VolumeConfirmationInjector
from tradeschool.exercises.charts.patterns.wyckoff import WyckoffInjector

_INJECTORS: dict[str, PatternInjector] = {
    injector.name: injector
    for injector in (
        FakeoutInjector(),
        MaContextInjector(),
        OscillatorReadingInjector(),
        MacdCrossInjector(),
        FibonacciInjector(),
        VolumeConfirmationInjector(),
        WyckoffInjector(),
        DerivativesInjector(),
        CandleReactionInjector(),
        CvdDivergenceInjector(),
        # m34-l1: the SMC dialect's two zones. Both plant a ground-truth `Band` (never drawn on an
        # exercise chart — that would be the answer) and both feed a figure AND an exercise.
        OriginZoneInjector(),
        ImbalanceInjector(),
        # m15: diagonal geometry. The first injectors to draw a `Diagonal`, and the first family born
        # BIDIRECTIONAL — the bull-only rule the two above carry is a named exception to it, not the
        # house style (see `test_chart_bands.py` §3b and `test_chart_diagonals.py`).
        TrendChannelInjector(),
        ConvergingLinesInjector(),
        # m16: the volatility cycle, and the first injector to drive the zero-centred momentum pane.
        VolatilityBandsInjector(),
        # m23-l2: the first injector to return a SECOND candle panel — the same stretch aggregated to a
        # coarser frame, which is the only way to ask a question about the relationship between two.
        MultiTimeframeInjector(),
        # Figure-only injectors: shapes whose whole point is the resolution, so no exercise uses them.
        MarketStructureInjector(),
        LiquiditySweepInjector(),
        StopLimitGapInjector(),
        TradeAnatomyInjector(),
    )
}


def has_injector(name: str) -> bool:
    return name in _INJECTORS


def get_injector(name: str) -> PatternInjector:
    try:
        return _INJECTORS[name]
    except KeyError as exc:
        raise KeyError(f"no pattern injector registered for {name!r}") from exc


def all_injectors() -> list[PatternInjector]:
    return list(_INJECTORS.values())
