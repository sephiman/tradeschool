# SPDX-License-Identifier: AGPL-3.0-only
"""Generic pattern-chart generator (Phase 2): the synthetic-chart contract with a pluggable injector.

A pure addition — the frozen divergence generator is untouched (§ freeze rule).
"""

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
from tradeschool.exercises.charts.patterns.base import ContextPanel
from tradeschool.exercises.charts.patterns.common import apply_level_guards
from tradeschool.exercises.charts.patterns.registry import get_injector, has_injector
from tradeschool.exercises.charts.types import Series
from tradeschool.exercises.types import ExerciseType


class PatternChartConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["pattern_chart"]
    prompt: LocalizedText
    injector: str
    n: int = 160
    indicator: Literal["rsi", "macd", "none", "oi", "cvd", "momentum"] | None = None
    targets: list[str]
    choices: list[str]
    explanation: LocalizedText | None = None

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not has_injector(self.injector):
            raise ValueError(f"unknown pattern injector {self.injector!r}")
        labels = set(get_injector(self.injector).labels)
        bad_targets = [t for t in self.targets if t not in labels]
        if not self.targets:
            raise ValueError("pattern_chart needs at least one target")
        if bad_targets:
            raise ValueError(f"targets not in injector {self.injector!r} labels: {bad_targets}")
        missing = [t for t in self.targets if t not in self.choices]
        if missing:
            raise ValueError(f"choices must include every target; missing {missing}")
        bad_choices = [c for c in self.choices if c not in labels]
        if bad_choices:
            raise ValueError(f"choices not in injector {self.injector!r} labels: {bad_choices}")
        return self


@dataclass
class FullPatternChart:
    """Full generated chart INCLUDING the warm-up prefix (for the dev export's reproducible RSI)."""

    label: str
    warmup: int
    indicator: str
    series: Series  # full (warmup + visible)
    rsi: list[float]
    macd_line: list[float]
    macd_signal: list[float]
    macd_hist: list[float]
    overlays: dict[str, list[float]]  # full-length lines over the close series
    levels: list[dict[str, object]]
    #: sloped lines (m15), bar indices already converted to VISIBLE coords like `annotations`.
    diagonals: list[dict[str, object]]
    annotations: list[dict[str, object]]  # visible coords
    #: shaded price zones (m34). Ground truth: `_instantiate` drops them from the pre-answer payload and
    #: `grade` reveals them. Price-space, so unlike `annotations` there is no warm-up coord to convert.
    bands: list[dict[str, object]]
    oi: list[float]  # full-length open-interest series (empty unless the injector supplies it)
    cvd: list[float]  # full-length cumulative-volume-delta series (empty unless supplied)
    #: full-length zero-centred pane series and its optional state row (empty unless supplied).
    momentum: list[float]
    momentum_state: list[float]
    #: the second candle panel (m23-l2), still carrying its own warm-up prefix. Public, unlike `bands`
    #: — see `ContextPanel`.
    context: ContextPanel | None


def _pane(values: np.ndarray | None) -> list[float]:
    """An optional pane series, rounded — absent injectors get `[]` and no payload key."""
    return [round(float(x), 4) for x in values.tolist()] if values is not None else []


def _full(config: PatternChartConfig, seed: int) -> FullPatternChart:
    rng = np.random.default_rng(seed)
    injector = get_injector(config.injector)
    target = config.targets[int(rng.integers(0, len(config.targets)))]
    result = injector.build(rng, config.n, target)
    close_full = result.close_full
    # An injector may ship its own OHLC (to shape wicks/bodies build_series would randomize); else
    # derive candles from the close path as usual.
    series = result.candles_full if result.candles_full is not None else build_series(rng, close_full)
    if result.candles_full is None and result.volume_full is not None:
        series.volume = [round(float(v), 2) for v in result.volume_full.tolist()]
    # A drawn level's contract with the candles, enforced here and in the figure builder alike so a
    # level never renders at a price the price action contradicts (see `LevelGuard`).
    apply_level_guards(series, result.level_guards)
    line, signal, hist = macd(close_full)
    w = result.warmup
    indicator = config.indicator or injector.indicator
    return FullPatternChart(
        label=result.label,
        warmup=w,
        indicator=indicator,
        series=series,
        rsi=[round(float(x), 2) for x in rsi(close_full)],
        macd_line=[round(float(x), 4) for x in line],
        macd_signal=[round(float(x), 4) for x in signal],
        macd_hist=[round(float(x), 4) for x in hist],
        overlays={k: [round(float(x), 2) for x in v] for k, v in result.overlays.items()},
        oi=([round(float(x), 2) for x in result.oi_full.tolist()] if result.oi_full is not None else []),
        cvd=([round(float(x), 2) for x in result.cvd_full.tolist()] if result.cvd_full is not None else []),
        momentum=_pane(result.momentum_full),
        momentum_state=_pane(result.momentum_state_full),
        context=result.context,
        levels=[{"price": lv.price, "label": lv.label, "kind": lv.kind} for lv in result.levels],
        diagonals=[
            {
                "start": d.start - w, "end": d.end - w,
                "start_price": d.start_price, "end_price": d.end_price,
                "label": d.label, "kind": d.kind,
            }
            for d in result.diagonals
        ],
        bands=[
            {"low": b.low, "high": b.high, "label": b.label, "kind": b.kind} for b in result.bands
        ],
        annotations=[
            {"index": a.index - w, "kind": a.kind, "label": a.label}
            for a in result.annotations
            if a.index - w >= 0
        ],
    )


def _instantiate(
    config: PatternChartConfig, seed: int
) -> tuple[str, list[dict[str, object]], dict[str, object]]:
    f = _full(config, seed)
    w = f.warmup
    s = f.series
    series = Series(
        time=s.time[w:], open=s.open[w:], high=s.high[w:], low=s.low[w:],
        close=s.close[w:], volume=s.volume[w:],
    )
    payload: dict[str, object] = {
        "series": asdict(series),
        "rsi": f.rsi[w:],
        "macd": {"line": f.macd_line[w:], "signal": f.macd_signal[w:], "hist": f.macd_hist[w:]},
        "indicator": f.indicator,
        "choices": list(config.choices),
        "overlays": {k: v[w:] for k, v in f.overlays.items()},
        "levels": f.levels,
        # `f.bands` is deliberately absent: a shaded zone drawn on the chart IS the answer to the
        # question that asks the learner to find it (m34). Bands reach the client only through
        # `grade()`'s `correct_answer`, and `test_chart_bands.py` asserts this key can never appear.
    }
    if f.oi:
        payload["oi"] = f.oi[w:]
    if f.cvd:
        payload["cvd"] = f.cvd[w:]
    if f.momentum:
        payload["momentum"] = f.momentum[w:]
    if f.momentum_state:
        payload["momentum_state"] = f.momentum_state[w:]
    if f.diagonals:
        # PUBLIC, unlike `bands`: a diagonal is the line the question is asked against, so withholding
        # it would leave nothing on the chart to judge. Conditional like `oi`/`cvd` so an injector that
        # draws none keeps exactly the payload keys it always had.
        payload["diagonals"] = f.diagonals
    if f.context is not None:
        # The second panel (m23-l2), trimmed at the same instant the main one is — which is why its
        # `ratio` divides the warm-up exactly. `ratio` itself stays out of the payload: it would say
        # in JSON which panel is the aggregate, and that is the question one of the exercises asks.
        c = f.context.series
        k = w // f.context.ratio
        payload["context"] = {
            "series": asdict(
                Series(time=c.time[k:], open=c.open[k:], high=c.high[k:], low=c.low[k:],
                       close=c.close[k:], volume=c.volume[k:])
            ),
            "position": f.context.position,
        }
    return f.label, f.annotations, payload


class PatternChartGenerator(ExerciseGenerator):
    type: ClassVar[ExerciseType] = ExerciseType.PATTERN_CHART

    def parse_config(self, raw: Mapping[str, object]) -> PatternChartConfig:
        return PatternChartConfig.model_validate(dict(raw))

    def full_data(self, config: PatternChartConfig, seed: int) -> FullPatternChart:
        """Full generated chart incl. warm-up rows — for the dev data export (reproducible RSI)."""
        return _full(config, seed)

    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        assert isinstance(config, PatternChartConfig)
        _, _, payload = _instantiate(config, seed)
        return GeneratedInstance(prompt=config.prompt.get(locale), payload=payload)

    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        assert isinstance(config, PatternChartConfig)
        chosen = answer.get("label")
        if not isinstance(chosen, str):
            raise InvalidAnswerError("expected a 'label' choice")
        # `_full` rather than `_instantiate`: grading now also reveals the ground-truth `bands`, and
        # `_instantiate` is unpacked as a 3-tuple at ~30 call sites across the test suites. `_instantiate`
        # is itself `_full` plus the warm-up trim, and `FullPatternChart.annotations` are already in
        # visible coords, so this yields byte-identical label/annotations for every existing injector —
        # asserted, not assumed, by `test_chart_bands.py::
        # test_grading_is_identical_whether_read_from_full_or_instantiate`.
        f = _full(config, seed)
        revealed: dict[str, object] = {"label": f.label, "annotations": f.annotations}
        if f.bands:
            # Conditional, like the `oi`/`cvd` payload keys: every pre-existing injector plants no band,
            # so its graded answer keeps exactly the two keys it always had.
            revealed["bands"] = f.bands
        return GradeResult(
            correct=chosen == f.label,
            correct_answer=revealed,
            explanation=config.explanation.get(locale) if config.explanation else None,
        )
