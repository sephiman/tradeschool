# SPDX-License-Identifier: AGPL-3.0-only
"""Synthetic chart generator: base engine + a pattern injector (§3.3). The seed picks the planted
pattern and builds the candles; grading re-derives the same pattern from the seed, so the ground
truth is exact and never travels to the client before answering."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import ClassVar, Literal, Self

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.base import (
    ExerciseGenerator,
    GeneratedInstance,
    GradeResult,
    InvalidAnswerError,
)
from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.indicators import macd, rsi
from tradeschool.exercises.charts.injectors import RsiDivergenceInjector
from tradeschool.exercises.charts.types import DivergenceType, Series
from tradeschool.exercises.types import ExerciseType

_INJECTOR = RsiDivergenceInjector()


class SyntheticChartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["synthetic_chart"]
    prompt: LocalizedText
    n: int = 160
    indicator: Literal["rsi", "macd"] = "rsi"
    targets: list[DivergenceType]
    choices: list[DivergenceType]
    explanation: LocalizedText | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.targets:
            raise ValueError("synthetic_chart needs at least one target")
        missing = set(self.targets) - set(self.choices)
        if missing:
            raise ValueError(f"choices must include every target; missing {sorted(m.value for m in missing)}")
        return self


@dataclass
class FullChart:
    """The complete generated chart INCLUDING the warm-up prefix — used to render the visible
    window and, for dev export, to make the RSI fully reproducible from the raw OHLC."""

    target: DivergenceType
    warmup: int
    series: Series  # full (warmup + visible)
    rsi: list[float]
    macd_line: list[float]
    macd_signal: list[float]
    macd_hist: list[float]
    swing1: int | None  # visible coords, or None
    swing2: int | None


def _full(config: SyntheticChartConfig, seed: int) -> FullChart:
    rng = np.random.default_rng(seed)
    target = config.targets[int(rng.integers(0, len(config.targets)))]
    close_full, warmup, s1_full, s2_full = _INJECTOR.build(rng, config.n, target, config.indicator)
    series_full = build_series(rng, close_full)
    macd_line, macd_signal, macd_hist = macd(close_full)
    return FullChart(
        target=target,
        warmup=warmup,
        series=series_full,
        rsi=[round(float(x), 2) for x in rsi(close_full)],
        macd_line=[round(float(x), 4) for x in macd_line],
        macd_signal=[round(float(x), 4) for x in macd_signal],
        macd_hist=[round(float(x), 4) for x in macd_hist],
        swing1=(s1_full - warmup) if s1_full is not None else None,
        swing2=(s2_full - warmup) if s2_full is not None else None,
    )


def _instantiate(
    config: SyntheticChartConfig, seed: int
) -> tuple[DivergenceType, int | None, int | None, dict[str, object]]:
    f = _full(config, seed)
    w = f.warmup
    s = f.series
    # Drop the warm-up prefix from everything the learner sees (real charts never show it), so the
    # oscillators are already converged at the left edge.
    series = Series(
        time=s.time[w:],
        open=s.open[w:],
        high=s.high[w:],
        low=s.low[w:],
        close=s.close[w:],
        volume=s.volume[w:],
    )
    payload: dict[str, object] = {
        "series": asdict(series),
        "rsi": f.rsi[w:],
        "macd": {"line": f.macd_line[w:], "signal": f.macd_signal[w:], "hist": f.macd_hist[w:]},
        "indicator": config.indicator,
        "choices": [c.value for c in config.choices],
    }
    return f.target, f.swing1, f.swing2, payload


class SyntheticChartGenerator(ExerciseGenerator):
    type: ClassVar[ExerciseType] = ExerciseType.SYNTHETIC_CHART

    def parse_config(self, raw: Mapping[str, object]) -> SyntheticChartConfig:
        return SyntheticChartConfig.model_validate(dict(raw))

    def full_data(self, config: SyntheticChartConfig, seed: int) -> FullChart:
        """Full generated chart incl. warm-up rows — for the dev data export (reproducible RSI)."""
        return _full(config, seed)

    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        assert isinstance(config, SyntheticChartConfig)
        _, _, _, payload = _instantiate(config, seed)
        return GeneratedInstance(prompt=config.prompt.get(locale), payload=payload)

    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        assert isinstance(config, SyntheticChartConfig)
        chosen = answer.get("divergence")
        if not isinstance(chosen, str):
            raise InvalidAnswerError("expected a 'divergence' choice")
        target, s1, s2, _ = _instantiate(config, seed)
        return GradeResult(
            correct=chosen == target.value,
            correct_answer={"divergence": target.value, "swing1": s1, "swing2": s2},
            explanation=config.explanation.get(locale) if config.explanation else None,
        )
