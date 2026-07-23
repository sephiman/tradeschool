# SPDX-License-Identifier: AGPL-3.0-only
"""Chart scenario value objects."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DivergenceType(StrEnum):
    NONE = "none"
    BULLISH_REGULAR = "bullish_regular"
    BEARISH_REGULAR = "bearish_regular"
    BULLISH_HIDDEN = "bullish_hidden"
    BEARISH_HIDDEN = "bearish_hidden"


@dataclass
class Series:
    time: list[int]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


@dataclass
class ChartScenario:
    series: Series
    rsi: list[float]
    macd: list[float]
    macd_signal: list[float]
    macd_hist: list[float]
    indicator: str  # "rsi" | "macd" — the oscillator the divergence lives on
    # Ground truth (never sent before answering):
    divergence: DivergenceType
    swing1: int | None
    swing2: int | None
