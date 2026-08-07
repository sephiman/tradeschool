# SPDX-License-Identifier: AGPL-3.0-only
"""Fixture chart generator: a curated bank of frozen OHLC scenarios (§3.2), selected by the seed.

The fallback for concepts that are hard to synthesize; each fixture carries its own label.
"""

from __future__ import annotations

import random
from collections.abc import Mapping
from typing import ClassVar, Literal, Self

from pydantic import BaseModel, ConfigDict, model_validator

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.base import (
    ExerciseGenerator,
    GeneratedInstance,
    GradeResult,
    InvalidAnswerError,
)
from tradeschool.exercises.charts.types import DivergenceType
from tradeschool.exercises.types import ExerciseType


class FixtureSeries(BaseModel):
    model_config = ConfigDict(extra="forbid")
    time: list[int]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: DivergenceType
    indicator: str = "rsi"
    series: FixtureSeries
    rsi: list[float]
    macd_line: list[float]
    macd_signal: list[float]
    macd_hist: list[float]
    swing1: int | None = None
    swing2: int | None = None


class FixtureChartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["fixture_chart"]
    prompt: LocalizedText
    choices: list[DivergenceType]
    fixtures: list[Fixture]
    explanation: LocalizedText | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.fixtures:
            raise ValueError("fixture_chart needs at least one fixture")
        missing = {f.label for f in self.fixtures} - set(self.choices)
        if missing:
            names = sorted(m.value for m in missing)
            raise ValueError(f"choices must include every fixture label; missing {names}")
        return self


class FixtureChartGenerator(ExerciseGenerator):
    type: ClassVar[ExerciseType] = ExerciseType.FIXTURE_CHART

    def parse_config(self, raw: Mapping[str, object]) -> FixtureChartConfig:
        return FixtureChartConfig.model_validate(dict(raw))

    def _pick(self, config: FixtureChartConfig, seed: int) -> Fixture:
        return config.fixtures[random.Random(seed).randrange(len(config.fixtures))]

    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        assert isinstance(config, FixtureChartConfig)
        fixture = self._pick(config, seed)
        payload: dict[str, object] = {
            "series": fixture.series.model_dump(),
            "rsi": fixture.rsi,
            "macd": {"line": fixture.macd_line, "signal": fixture.macd_signal, "hist": fixture.macd_hist},
            "indicator": fixture.indicator,
            "choices": [c.value for c in config.choices],
        }
        return GeneratedInstance(prompt=config.prompt.get(locale), payload=payload)

    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        assert isinstance(config, FixtureChartConfig)
        chosen = answer.get("divergence")
        if not isinstance(chosen, str):
            raise InvalidAnswerError("expected a 'divergence' choice")
        fixture = self._pick(config, seed)
        return GradeResult(
            correct=chosen == fixture.label.value,
            correct_answer={
                "divergence": fixture.label.value,
                "swing1": fixture.swing1,
                "swing2": fixture.swing2,
            },
            explanation=config.explanation.get(locale) if config.explanation else None,
        )
