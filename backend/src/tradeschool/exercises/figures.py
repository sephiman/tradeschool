# SPDX-License-Identifier: AGPL-3.0-only
"""Lesson figures: frozen-seed charts from the same injectors as exercises, but showing the RESOLUTION.

A figure spec is content — its seed is hand-picked and frozen forever. The build is strictly additive
(`append_resolution` on the injector's unchanged `build()`) and never feeds back into exercise mode.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal, Self

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict, model_validator

from tradeschool.content.schema import LocalizedText
from tradeschool.exercises.charts.engine import build_series
from tradeschool.exercises.charts.indicators import ema, macd, rsi
from tradeschool.exercises.charts.injectors import RsiDivergenceInjector
from tradeschool.exercises.charts.patterns.base import ContextPanel, Diagonal, LevelGuard
from tradeschool.exercises.charts.patterns.common import (
    append_linear_continuation,
    append_resolution,
    apply_level_guards,
)
from tradeschool.exercises.charts.patterns.diagonals import extended as extend_diagonal
from tradeschool.exercises.charts.patterns.registry import get_injector, has_injector
from tradeschool.exercises.charts.types import DivergenceType, Series

_DIVERGENCE = RsiDivergenceInjector()
_DIR_SIGN = {"up": 1.0, "down": -1.0, "flat": 0.0}
# Default resolution direction for a divergence figure (regular = reversal, hidden = continuation).
_DIVERGENCE_DIR = {
    "bullish_regular": 1.0, "bullish_hidden": 1.0,
    "bearish_regular": -1.0, "bearish_hidden": -1.0, "none": 0.0,
}
# Default resolution direction for pattern figures whose direction is unambiguous from the label.
# Side/impulse-dependent injectors (fakeout, fibonacci, volume_confirmation, derivatives, macd_cross)
# are NOT listed — those figures must state `resolution` explicitly, since the direction depends on
# the seed.
_PATTERN_DIR: dict[str, dict[str, float]] = {
    "wyckoff": {"accumulation": 1.0, "distribution": -1.0, "none": 0.0},
    "ma_context": {"uptrend": 1.0, "downtrend": -1.0, "range": 0.0},
    "oscillator_reading": {"overbought": 1.0, "oversold": -1.0, "neutral": 0.0},
    # A CVD divergence resolves against the extreme it refused (absorbed selling -> markup, and the
    # mirror). `cvd_confirms` is deliberately absent: the confirmed break continues in whichever
    # direction that seed built, so such a figure must state `resolution` explicitly.
    "cvd_divergence": {"cvd_bullish_divergence": 1.0, "cvd_bearish_divergence": -1.0},
}
_RESOLUTION_CANDLES = 24


class FigureResolution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["up", "down", "flat"]
    strength: float = 0.18


class FigurePanel(BaseModel):
    model_config = ConfigDict(extra="forbid")
    generator: Literal["pattern_chart", "synthetic_chart"]
    injector: str | None = None  # pattern_chart only
    target: str  # the specific label / divergence this figure plants
    seed: int  # frozen, hand-picked
    n: int = 160
    indicator: Literal["rsi", "macd", "none", "oi", "cvd", "momentum"] | None = None
    show_resolution: bool = True
    resolution: FigureResolution | None = None  # explicit direction; else a per-generator default

    @model_validator(mode="after")
    def _check(self) -> Self:
        if self.generator == "pattern_chart":
            if not self.injector or not has_injector(self.injector):
                raise ValueError(f"figure panel: unknown injector {self.injector!r}")
            if self.target not in get_injector(self.injector).labels:
                raise ValueError(f"figure panel: target {self.target!r} not a {self.injector} label")
        else:
            try:
                DivergenceType(self.target)
            except ValueError as exc:
                raise ValueError(f"figure panel: bad divergence {self.target!r}") from exc
        return self


class FigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    # Permanent identity, chosen once (defaults to the id at creation) — the same contract as the
    # manifest's keys, so a display renumbering never touches what hangs off a figure.
    key: str = ""
    kind: Literal["chart", "svg"] = "chart"
    svg: str | None = None  # kind=svg: a component name the frontend renders (e.g. candle anatomy)
    caption: LocalizedText
    panels: list[FigurePanel] = []

    @model_validator(mode="after")
    def _check(self) -> Self:
        if not self.key:
            self.key = self.id
        if self.kind == "chart" and not self.panels:
            raise ValueError(f"figure {self.id!r}: a chart figure needs at least one panel")
        if self.kind == "svg" and not self.svg:
            raise ValueError(f"figure {self.id!r}: an svg figure needs an 'svg' name")
        return self


def _round(values: object, ndigits: int) -> list[float]:
    arr = np.asarray(values, dtype=float)
    return [round(float(x), ndigits) for x in arr.tolist()]


def _panel_payload(panel: FigurePanel) -> dict[str, object]:
    rng = np.random.default_rng(panel.seed)
    overlays_raw: dict[str, list[float]] = {}
    levels: list[dict[str, object]] = []
    bands: list[dict[str, object]] = []
    level_guards: list[LevelGuard] = []
    annotations: list[dict[str, object]] = []
    oi_full: np.ndarray | None = None
    cvd_full: np.ndarray | None = None
    momentum_full: np.ndarray | None = None
    momentum_state_full: np.ndarray | None = None
    volume_full: np.ndarray | None = None
    candles_override: Series | None = None
    resolution_hint: float | None = None
    diagonals_raw: list[Diagonal] = []
    injector_obj: object = None
    context: ContextPanel | None = None

    if panel.generator == "synthetic_chart":
        target = DivergenceType(panel.target)
        indicator: str = panel.indicator or "rsi"
        close_full, warmup, s1, s2 = _DIVERGENCE.build(rng, panel.n, target, indicator)
        swing_kind = "high" if target.value.startswith("bearish") else "low"
        for idx, name in ((s1, "1"), (s2, "2")):
            if idx is not None and idx - warmup >= 0:
                annotations.append({"index": idx - warmup, "kind": swing_kind, "label": name})
        default_dir = _DIVERGENCE_DIR.get(target.value, 0.0)
    else:
        injector = get_injector(panel.injector or "")
        result = injector.build(rng, panel.n, panel.target)
        close_full, warmup = result.close_full, result.warmup
        indicator = panel.indicator or injector.indicator
        overlays_raw = {k: list(v) for k, v in result.overlays.items()}
        levels = [{"price": lv.price, "label": lv.label, "kind": lv.kind} for lv in result.levels]
        # A figure DRAWS the band an exercise must withhold: the zone is the resolution being shown
        # (m34's origin zone and imbalance), which is the same asymmetry `show_resolution` already is.
        bands = [{"low": b.low, "high": b.high, "label": b.label, "kind": b.kind} for b in result.bands]
        level_guards = result.level_guards
        # Figure-only richer annotations (e.g. Wyckoff phase labels A-E) come from an optional
        # `figure_annotations` method — never from build(), so exercise output is untouched.
        fig_ann = getattr(injector, "figure_annotations", None)
        raw_ann = fig_ann(panel.target, panel.n) if callable(fig_ann) else result.annotations
        annotations = [
            {"index": a.index - warmup, "kind": a.kind, "label": a.label}
            for a in raw_ann
            if a.index - warmup >= 0
        ]
        oi_full, volume_full = result.oi_full, result.volume_full
        cvd_full = result.cvd_full
        momentum_full, momentum_state_full = result.momentum_full, result.momentum_state_full
        candles_override = result.candles_full
        resolution_hint = result.resolution_hint
        context = result.context
        diagonals_raw = list(result.diagonals)
        injector_obj = injector
        default_dir = _PATTERN_DIR.get(panel.injector or "", {}).get(panel.target, 0.0)

    reaction_len = len(close_full)  # the pre-resolution region (an injector's planted candles)
    if panel.show_resolution:
        # An explicit spec direction wins; else the injector's own hint (it knows the planted form);
        # else the per-injector default. A gentler leg for candle reactions than the generic 0.18.
        if panel.resolution:
            direction = _DIR_SIGN[panel.resolution.direction]
        elif resolution_hint is not None:
            direction = resolution_hint
        else:
            direction = default_dir
        if panel.resolution:
            strength = panel.resolution.strength
        else:
            strength = 0.12 if candles_override is not None else 0.18  # gentler leg for candle reactions
        before = len(close_full)
        close_full = append_resolution(rng, close_full, direction, strength, _RESOLUTION_CANDLES)
        added = len(close_full) - before
        if oi_full is not None:
            oi_dir = float(np.sign(oi_full[-1] - oi_full[0]))
            oi_full = append_resolution(rng, oi_full, oi_dir, 0.12, added)
        if cvd_full is not None:
            # Linear space — a CVD legitimately sits at or below zero, so the log-space leg the price
            # and OI panes use would be meaningless here. It continues in the RESOLUTION's direction
            # (the absorbed side taking control is the whole point of the figure) rather than in
            # whichever direction it happened to be travelling.
            cvd_full = append_linear_continuation(rng, cvd_full, direction, 0.35, added)
        if volume_full is not None:
            base = float(np.median(volume_full))
            extra = base * (0.7 + 0.5 * np.abs(rng.normal(0.0, 1.0, added)))
            volume_full = np.concatenate([volume_full, extra])

    if candles_override is None:
        series = build_series(rng, close_full)
        if volume_full is not None:
            series.volume = _round(volume_full, 2)
    elif not panel.show_resolution:
        series = candles_override  # honor the injector's own OHLC (planted wicks), no continuation
    else:
        # Continuation for a candle-reaction figure: derive candles over the extended close, then
        # splice the injector's planted reaction candles (their wicks) back over the reaction region.
        series = build_series(rng, close_full)
        for i in range(reaction_len):
            series.open[i] = candles_override.open[i]
            series.high[i] = candles_override.high[i]
            series.low[i] = candles_override.low[i]
            series.close[i] = candles_override.close[i]
            series.volume[i] = candles_override.volume[i]
    # Same level/candle contract the exercise generator applies. The guards' bar indices are anchored
    # at the start of the series, so an appended resolution leg leaves them pointing at the same bars.
    apply_level_guards(series, level_guards)
    line, signal, hist = macd(close_full)
    w = warmup
    overlays: dict[str, list[float]] = {}
    for name in overlays_raw:  # recompute EMA overlays over the extended close (keys like "ema20")
        m = re.search(r"(\d+)$", name)
        overlays[name] = _round(ema(close_full, int(m.group(1))), 2) if m else overlays_raw[name]
    # Overlays an EMA period cannot express — m16's Bollinger/Keltner envelopes, which need the derived
    # OHLC, not just the close. Same optional-method precedent as `figure_annotations` above: the
    # injector recomputes them over the EXTENDED series, so the envelopes run to the right edge instead
    # of stopping where the exercise window did. Without it a squeeze figure would draw its bands over
    # the compression and then nothing over the expansion, which is the half the figure exists for.
    recompute = getattr(injector_obj, "figure_overlays", None)
    if callable(recompute):
        overlays.update({k: _round(v, 2) for k, v in recompute(close_full, series).items()})
    if momentum_full is not None:
        # Same reason, same shape: the pane series is a function of the price, so it is recomputed over
        # the extended one rather than continued by a synthetic leg the way OI and CVD are.
        pane = getattr(injector_obj, "figure_momentum", None)
        if callable(pane):
            momentum_full, momentum_state_full = pane(close_full, series)
    if context is not None:
        # ...and the third hook, for the same reason again: the second panel (m23-l2) is an aggregation
        # OF these candles, so an aggregate built before the resolution leg would go blank across
        # exactly the stretch the figure exists to show.
        recompute_context = getattr(injector_obj, "figure_context", None)
        if callable(recompute_context):
            context = ContextPanel(
                series=recompute_context(close_full, series),
                ratio=context.ratio,
                position=context.position,
            )
    # The projection is the whole point of a diagonal: a break is only visible against the line carried
    # PAST the bars that drew it, so a figure re-anchors every diagonal to its own right edge.
    diagonals = [
        {
            "start": d.start - w, "end": d.end - w,
            "start_price": d.start_price, "end_price": d.end_price,
            "label": d.label, "kind": d.kind,
        }
        for d in (extend_diagonal(raw, len(series.close) - 1) for raw in diagonals_raw)
    ]

    payload: dict[str, object] = {
        "series": {
            "time": series.time[w:], "open": series.open[w:], "high": series.high[w:],
            "low": series.low[w:], "close": series.close[w:], "volume": series.volume[w:],
        },
        "rsi": _round(rsi(close_full), 2)[w:],
        "macd": {"line": _round(line, 4)[w:], "signal": _round(signal, 4)[w:], "hist": _round(hist, 4)[w:]},
        "indicator": indicator,
        "overlays": {k: v[w:] for k, v in overlays.items()},
        "levels": levels,
        "diagonals": diagonals,
        "bands": bands,
        "annotations": annotations,
    }
    if oi_full is not None:
        payload["oi"] = _round(oi_full, 2)[w:]
    if cvd_full is not None:
        payload["cvd"] = _round(cvd_full, 2)[w:]
    if momentum_full is not None:
        payload["momentum"] = _round(momentum_full, 4)[w:]
    if momentum_state_full is not None:
        payload["momentum_state"] = _round(momentum_state_full, 4)[w:]
    if context is not None:
        c, k = context.series, w // context.ratio
        payload["context"] = {
            "series": {
                "time": c.time[k:], "open": c.open[k:], "high": c.high[k:],
                "low": c.low[k:], "close": c.close[k:], "volume": c.volume[k:],
            },
            "position": context.position,
        }
    return payload


def build_figure(spec: FigureSpec, locale: str) -> dict[str, object]:
    data: dict[str, object] = {"id": spec.id, "kind": spec.kind, "caption": spec.caption.get(locale)}
    if spec.kind == "svg":
        data["svg"] = spec.svg
    else:
        data["panels"] = [_panel_payload(p) for p in spec.panels]
    return data


def load_figures(content_dir: Path) -> dict[str, FigureSpec]:
    figures: dict[str, FigureSpec] = {}
    keys: set[str] = set()
    figures_dir = content_dir / "figures"
    if not figures_dir.exists():
        return figures
    for path in sorted(figures_dir.glob("*.yaml")):
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        spec = FigureSpec.model_validate(raw)
        if spec.id != path.stem:
            raise ValueError(f"figure id {spec.id!r} must match filename {path.stem!r}")
        if spec.key in keys:
            raise ValueError(f"duplicate figure key {spec.key!r} ({spec.id})")
        keys.add(spec.key)
        figures[spec.id] = spec
    return figures
