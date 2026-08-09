# SPDX-License-Identifier: AGPL-3.0-only
"""The cross-frame contract (m20-l2): the upper panel IS the lower one, aggregated.

m20-l2's first claim is that a timeframe change adds no information — "one 4h candle IS four 1h
candles" — so the figure that teaches it must not merely look aggregated. Every upper bar is checked
against its four lower ones TO THE CENT, out of the payload the client actually receives.

The checker is written so it can FAIL: §1b feeds it deliberately corrupted aggregations, one per
field, and requires each to be caught. A contract only ever exercised on correct data is a contract
nobody has seen say no.
"""

from __future__ import annotations

from dataclasses import replace

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns.common import TAIL
from tradeschool.exercises.charts.patterns.multi_timeframe import RATIO, WARMUP, aggregate
from tradeschool.exercises.charts.patterns.registry import get_injector
from tradeschool.exercises.charts.types import Series
from tradeschool.exercises.figures import FigureSpec, build_figure
from tradeschool.exercises.pattern_chart import PatternChartConfig, PatternChartGenerator, _instantiate

_INJECTOR = "multi_timeframe"
_N = 130
_SEEDS = 120
_SHAPE_LABELS = ("pullback_against_trend", "continuation_with_trend", "higher_frame_ranges")
_POSITION_LABELS = ("top_is_higher_frame", "bottom_is_higher_frame")
_ALL = (*_SHAPE_LABELS, *_POSITION_LABELS)


def _config(targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": _INJECTOR,
         "n": n, "indicator": "none", "targets": targets, "choices": list(get_injector(_INJECTOR).labels)}
    )


def _series(payload: dict) -> Series:
    return Series(**payload["series"])


def _context(payload: dict) -> tuple[Series, str]:
    ctx = payload["context"]
    return Series(**ctx["series"]), str(ctx["position"])


# --- 1. the aggregation contract ------------------------------------------------------------------


def coherence_errors(lower: Series, upper: Series, ratio: int = RATIO) -> list[str]:
    """Every way the upper panel could fail to BE the lower one aggregated. Empty means coherent.

    Deliberately exhaustive rather than early-returning: a corrupted instance should name every field
    it broke, which is what makes §1b's per-field red-first meaningful.
    """
    errors: list[str] = []
    if len(upper.close) != len(lower.close) // ratio:
        errors.append(f"bar count {len(upper.close)} != {len(lower.close)}//{ratio}")
    for g in range(min(len(upper.close), len(lower.close) // ratio)):
        lo, hi = g * ratio, (g + 1) * ratio
        if upper.open[g] != lower.open[lo]:
            errors.append(f"bar {g}: open {upper.open[g]} != first open {lower.open[lo]}")
        if upper.close[g] != lower.close[hi - 1]:
            errors.append(f"bar {g}: close {upper.close[g]} != last close {lower.close[hi - 1]}")
        if upper.high[g] != max(lower.high[lo:hi]):
            errors.append(f"bar {g}: high {upper.high[g]} != max {max(lower.high[lo:hi])}")
        if upper.low[g] != min(lower.low[lo:hi]):
            errors.append(f"bar {g}: low {upper.low[g]} != min {min(lower.low[lo:hi])}")
        if upper.volume[g] != round(sum(lower.volume[lo:hi]), 2):
            errors.append(f"bar {g}: volume {upper.volume[g]} != sum {round(sum(lower.volume[lo:hi]), 2)}")
        if upper.time[g] != lower.time[lo]:
            errors.append(f"bar {g}: time {upper.time[g]} != first time {lower.time[lo]}")
    return errors


@pytest.mark.parametrize("label", _ALL)
def test_upper_frame_is_the_exact_aggregation_of_the_lower_one(label: str) -> None:
    """To the cent, on the PUBLISHED panels — the numbers a learner's browser is handed."""
    config = _config([label])
    for seed in range(_SEEDS):
        _lbl, _ann, payload = _instantiate(config, seed)
        errors = coherence_errors(*(_series(payload), _context(payload)[0]))
        assert not errors, f"{label}/{seed}: {errors[:4]}"


def test_both_panels_start_at_the_same_bar() -> None:
    """The warm-up trims out of both frames at one instant, or the panels show different stretches."""
    assert WARMUP % RATIO == 0, "the warm-up must be a whole number of upper-frame bars"
    config = _config(list(_SHAPE_LABELS))
    for seed in range(40):
        _lbl, _ann, payload = _instantiate(config, seed)
        lower, (upper, _pos) = _series(payload), _context(payload)
        assert upper.time[0] == lower.time[0]
        assert upper.close[-1] == lower.close[-1], "both panels must end on the same close"
        # ...and the same total travel, because it is the same price.
        assert upper.high[: len(upper.high)] and max(upper.high) == max(lower.high)
        assert min(upper.low) == min(lower.low)


# --- 1b. red-first: the same checker, fed a corrupted aggregation ---------------------------------


def _corrupt(upper: Series, field: str) -> Series:
    """One cent, or one bar, in the wrong place — the smallest lie the contract has to catch."""
    g = len(upper.close) // 2
    changed = {f: list(getattr(upper, f)) for f in ("time", "open", "high", "low", "close", "volume")}
    if field == "bar_count":
        for f in changed:
            changed[f] = changed[f][:-1]
    elif field == "high":
        # The classic wrong aggregation: the group's LAST high instead of its extreme. It is only ever
        # wrong when some other bar in the group was higher, which is the normal case.
        changed["high"][g] = round(changed["high"][g] - 0.01, 2)
    elif field == "low":
        changed["low"][g] = round(changed["low"][g] + 0.01, 2)
    elif field == "volume":
        # The other classic: averaging the four volumes instead of summing them.
        changed["volume"][g] = round(changed["volume"][g] / RATIO, 2)
    else:
        changed[field][g] = round(changed[field][g] + 0.01, 2)
    return Series(**changed)


@pytest.mark.parametrize("field", ["bar_count", "time", "open", "high", "low", "close", "volume"])
def test_a_corrupted_aggregation_is_rejected(field: str) -> None:
    """RED FIRST. Each field broken on its own, on a chart that passes untouched."""
    config = _config(["pullback_against_trend"])
    _lbl, _ann, payload = _instantiate(config, 7)
    lower, (upper, _pos) = _series(payload), _context(payload)
    assert not coherence_errors(lower, upper), "the unmodified instance must be coherent"

    errors = coherence_errors(lower, _corrupt(upper, field))
    assert errors, f"corrupting {field} produced no error — the contract cannot fail"
    assert any(field.split("_")[0] in e for e in errors), f"{field} broken, reported as {errors[:2]}"


def test_the_aggregator_itself_rejects_a_hand_built_lie() -> None:
    """`aggregate` is the production side of the same claim, so it is checked against a mutated input.

    Moving ONE lower bar's high a cent above its group's must move the upper bar with it: an aggregate
    that ignored a lower candle would be a higher frame carrying information the lower one does not.
    """
    config = _config(["continuation_with_trend"])
    full = PatternChartGenerator().full_data(config, 3)
    lower = full.series
    assert full.context is not None
    before = aggregate(lower, RATIO)

    g, j = 5, 5 * RATIO + 1  # a bar in the middle of its own group, not on either edge
    lifted = replace(lower, high=[*lower.high[:j], round(before.high[g] + 0.01, 2), *lower.high[j + 1 :]])
    after = aggregate(lifted, RATIO)
    assert after.high[g] == round(before.high[g] + 0.01, 2), "the group's extreme ignored a lower bar"
    assert coherence_errors(lower, after), "an aggregate of DIFFERENT candles must not verify"


# --- 2. the relationship the lesson is named for, asserted on the instance -------------------------


def _turn(annotations: list[dict]) -> int:
    marks = [int(a["index"]) for a in annotations if a["label"] == "turn"]
    assert len(marks) == 1, f"expected exactly one turn marker, got {annotations}"
    return marks[0]


def _legs(payload: dict, annotations: list[dict]) -> tuple[float, float, int, int]:
    """(the lower-frame run, the whole window's travel, the turn bar, the last structural bar).

    Both in log terms and both measured to the last bar BEFORE the ambient tail, which is eight bars of
    deliberate signal-free noise and belongs to no leg.
    """
    close = np.asarray(payload["series"]["close"], dtype=float)
    k = len(close) - TAIL - 1
    turn = _turn(annotations)
    return float(np.log(close[k] / close[turn])), float(np.log(close[k] / close[0])), turn, k


def test_pullback_runs_against_a_higher_frame_that_survives_it() -> None:
    """The named error: a clean run on the lower frame, against an upper structure still intact."""
    config = _config(["pullback_against_trend"])
    for seed in range(_SEEDS):
        _lbl, ann, payload = _instantiate(config, seed)
        run, whole, turn, k = _legs(payload, ann)
        close = np.asarray(payload["series"]["close"], dtype=float)
        assert abs(run) > 0.03, f"seed {seed}: the lower-frame run is only {run:.3f}"
        assert np.sign(run) != np.sign(whole), f"seed {seed}: the run agrees with the higher frame"
        assert abs(whole) > 0.06, f"seed {seed}: no higher-frame trend to be inside ({whole:.3f})"
        # A PULLBACK, not a reversal: it gives back well under half of the impulse it interrupts...
        impulse = abs(float(np.log(close[turn] / close[0])))
        assert abs(run) / impulse < 0.55, f"seed {seed}: retraced {abs(run) / impulse:.0%} — a reversal"
        # ...and never undercuts the structure the higher frame built on the way (its early extreme).
        early = close[: int(0.45 * len(close))]
        held = close[k] > early.max() if whole > 0 else close[k] < early.min()
        assert held, f"seed {seed}: the pullback broke the higher frame's own structure"


def test_continuation_runs_with_the_higher_frame_and_makes_a_new_extreme() -> None:
    config = _config(["continuation_with_trend"])
    for seed in range(_SEEDS):
        _lbl, ann, payload = _instantiate(config, seed)
        run, whole, turn, k = _legs(payload, ann)
        close = np.asarray(payload["series"]["close"], dtype=float)
        assert abs(run) > 0.05, f"seed {seed}: the lower-frame run is only {run:.3f}"
        assert np.sign(run) == np.sign(whole), f"seed {seed}: the run fights the higher frame"
        # The difference that makes it a continuation rather than a pullback: it goes somewhere new.
        beyond = close[k] > close[:turn].max() if whole > 0 else close[k] < close[:turn].min()
        assert beyond, f"seed {seed}: a continuation must clear everything before its own turn"


def test_the_control_has_no_higher_frame_trend_to_be_inside() -> None:
    """The range: the same size of lower-frame run, and nothing above it for the run to relate to."""
    config = _config(["higher_frame_ranges"])
    for seed in range(_SEEDS):
        _lbl, ann, payload = _instantiate(config, seed)
        run, whole, _turn_bar, _k = _legs(payload, ann)
        assert abs(run) > 0.03, f"seed {seed}: the lower-frame run is only {run:.3f}"
        assert abs(whole) < 0.05, f"seed {seed}: the 'range' travelled {whole:.3f}"


def test_the_run_reads_the_same_on_both_frames() -> None:
    """Aggregation adds no information, so the two frames agree about the whole window's travel.

    Measured OPEN to close, not close to close: the upper frame's first close is the lower frame's
    FOURTH one, which is not the two panels disagreeing — it is what a coarser candle is.
    """
    config = _config(list(_SHAPE_LABELS))
    for seed in range(60):
        _lbl, _ann, payload = _instantiate(config, seed)
        lower, (upper, _pos) = _series(payload), _context(payload)
        lo = np.log(lower.close[-1] / lower.open[0])
        up = np.log(upper.close[-1] / upper.open[0])
        assert lo == pytest.approx(up, abs=1e-9), f"seed {seed}: the two frames disagree about the move"
        # ...and no upper bar invents a move: its body is inside the span its own four lower bars made.
        for g in range(len(upper.close)):
            group = lower.close[g * RATIO : (g + 1) * RATIO]
            assert min(group) - 1e-9 <= upper.close[g] <= max(group) + 1e-9, f"seed {seed}, bar {g}"


# --- 3. which panel contains the other -------------------------------------------------------------


def test_only_the_aggregate_s_POSITION_separates_the_two_ordering_labels() -> None:
    """The answer must be in the candles, so nothing else about the chart may move with the label."""
    lower_by_label: dict[str, list[float]] = {}
    for label in _POSITION_LABELS:
        _lbl, _ann, payload = _instantiate(_config([label]), 11)
        lower, (upper, position) = _series(payload), _context(payload)
        assert not coherence_errors(lower, upper)
        assert position == ("above" if label == "top_is_higher_frame" else "below")
        lower_by_label[label] = lower.close
    assert lower_by_label["top_is_higher_frame"] == lower_by_label["bottom_is_higher_frame"], (
        "one seed must draw the same price for both ordering labels — only the panel moves"
    )


def test_the_context_ratio_never_reaches_the_client() -> None:
    """It would answer 'which panel is the aggregate' in JSON, which is one of the two questions."""
    for label in _ALL:
        _lbl, _ann, payload = _instantiate(_config([label]), 2)
        assert set(payload["context"]) == {"series", "position"}, payload["context"].keys()


def test_the_shape_labels_all_put_the_context_above() -> None:
    """Context above, trigger below — the sequence discipline m20-l2 teaches, drawn rather than said."""
    for label in _SHAPE_LABELS:
        for seed in range(10):
            _lbl, _ann, payload = _instantiate(_config([label]), seed)
            assert _context(payload)[1] == "above", f"{label}/{seed}"


# --- 4. the figure path: the contract survives the appended resolution -----------------------------


def _figure_panel(target: str, seed: int, n: int = 160) -> dict:
    spec = FigureSpec.model_validate(
        {
            "id": "fig-test-timeframes",
            "caption": {"en": "x", "es": "x"},
            "panels": [
                {"generator": "pattern_chart", "injector": _INJECTOR, "target": target,
                 "seed": seed, "n": n, "indicator": "none"}
            ],
        }
    )
    panels = build_figure(spec, "en")["panels"]
    assert isinstance(panels, list)
    return panels[0]


@pytest.mark.parametrize("target", _SHAPE_LABELS)
def test_the_figure_aggregate_covers_the_resolution_leg_too(target: str) -> None:
    """A figure appends 24 lower bars; six upper ones must appear with them, still exact to the cent."""
    for seed in (1, 2, 3):
        panel = _figure_panel(target, seed)
        lower = Series(**panel["series"])
        upper = Series(**panel["context"]["series"])
        assert not coherence_errors(lower, upper), f"{target}/{seed}"
        # The resolution is on screen (that is what a figure is), and the upper panel grew with it.
        assert len(lower.close) == 160 + 24
        assert len(upper.close) == (160 + 24) // RATIO
