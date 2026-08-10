# SPDX-License-Identifier: AGPL-3.0-only
"""Marker and plan-line integrity: an annotation must be true of the bar it points at.

`plan` lines (entry, stop, target, a stop-limit's trigger and limit) are exempt from the level suite's
"the action reached it" rule — a stop the action reached is a stop that got hit — so without this file
they would be under no contract at all.

Two layers: a DISCOVERED sweep over every injector and figure for the invariants that hold for any
annotation, then per-injector geometry over hundreds of seeds. Older injectors' markers have layer 1
only — their positions come from `resolve_swing`, so pinning them to the candles would re-cut every
golden fingerprint.
"""

from __future__ import annotations

from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns.common import TAIL
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.figures import build_figure, load_figures
from tradeschool.exercises.pattern_chart import PatternChartConfig, PatternChartGenerator, _instantiate

_SEEDS = 300  # the wick that decides a pivot is a random draw, so a handful of seeds proves nothing
_N = 130
_KINDS = {"high", "low", "marker"}  # what the frontend maps to arrow-down / arrow-up / neutral dot
_CONTENT = Path(__file__).resolve().parents[2] / "content"

Payload = dict[str, object]
Annotations = list[dict[str, object]]


def _config(injector: str, targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": n, "targets": targets, "choices": list(get_injector(injector).labels)}
    )


def _series(payload: Payload) -> dict[str, list[float]]:
    s = payload["series"]
    assert isinstance(s, dict)
    return s


def _levels(payload: Payload) -> dict[str, float]:
    levels = payload["levels"]
    assert isinstance(levels, list)
    return {str(lv["label"]): float(str(lv["price"])) for lv in levels}


def _at(annotations: Annotations, label: str) -> int:
    hits = [int(str(a["index"])) for a in annotations if a["label"] == label]
    assert len(hits) == 1, f"expected exactly one {label!r} marker, got {hits}"
    return hits[0]


def _labelled(annotations: Annotations, label: str) -> list[int]:
    return [int(str(a["index"])) for a in annotations if a["label"] == label]


# --- 1. the discovered sweep: invariants every annotation owes ------------------------------------


def _injector_labels() -> list[tuple[str, str]]:
    return [(inj.name, label) for inj in all_injectors() for label in inj.labels]


@pytest.mark.parametrize(("injector", "label"), _injector_labels())
def test_every_annotation_is_renderable(injector: str, label: str) -> None:
    """Every annotation is in the visible window, of a known kind, labelled, and alone on its bar."""
    config = _config(injector, [label])
    for seed in range(40):
        _lbl, annotations, payload = _instantiate(config, seed)
        n = len(_series(payload)["close"])
        seen: set[int] = set()
        for a in annotations:
            idx, kind = int(str(a["index"])), str(a["kind"])
            assert 0 <= idx < n, f"seed {seed}: {injector}/{label} marker at {idx} outside [0,{n})"
            assert kind in _KINDS, f"seed {seed}: {injector}/{label} unknown marker kind {kind!r}"
            assert str(a["label"]), f"seed {seed}: {injector}/{label} marker with no label"
            assert idx not in seen, f"seed {seed}: {injector}/{label} two markers on bar {idx}"
            seen.add(idx)


def _figure_annotations() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for fid, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        panels = build_figure(spec, "en")["panels"]
        assert isinstance(panels, list)
        out += [(fid, i) for i, _p in enumerate(panels)]
    return out


@pytest.mark.parametrize(("figure_id", "panel"), _figure_annotations())
def test_figure_annotations_are_renderable(figure_id: str, panel: int) -> None:
    """The same contract on the figure path, which recomputes visible coords through its own code."""
    panels = build_figure(load_figures(_CONTENT)[figure_id], "en")["panels"]
    assert isinstance(panels, list)
    p = panels[panel]
    annotations = p["annotations"]
    assert isinstance(annotations, list)
    n = len(_series(p)["close"])
    seen: set[int] = set()
    for a in annotations:
        idx = int(str(a["index"]))
        assert 0 <= idx < n, f"{figure_id} panel{panel}: marker at {idx} outside [0,{n})"
        assert str(a["kind"]) in _KINDS, f"{figure_id} panel{panel}: unknown kind {a['kind']!r}"
        assert str(a["label"]), f"{figure_id} panel{panel}: marker with no label"
        assert idx not in seen, f"{figure_id} panel{panel}: two markers on bar {idx}"
        seen.add(idx)


# --- 2. market_structure (m08-l1): the ladder is what the labels say it is ------------------------


def _extreme_window(indices: list[int], k: int, n: int) -> tuple[int, int]:
    """The swing a marker owns, previous marker to next. The last one stops at the AMBIENT TAIL."""
    lo = indices[k - 1] if k > 0 else 0
    hi = indices[k + 1] + 1 if k + 1 < len(indices) else n - TAIL
    return lo, hi


@pytest.mark.parametrize("label", ["uptrend_ladder", "choch_after_uptrend"])
def test_pivot_markers_are_the_extreme_of_their_own_swing(label: str) -> None:
    """Each HH / HL / CHoCH marker sits on the bar whose WICK is its swing's extreme — not near it."""
    config = _config("market_structure", [label])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        n = len(s["close"])
        idx = [int(str(a["index"])) for a in annotations]
        assert idx == sorted(idx), f"seed {seed}: markers out of order {idx}"
        for k, a in enumerate(annotations):
            i, kind = int(str(a["index"])), str(a["kind"])
            lo, hi = _extreme_window(idx, k, n)
            edge = s["high"] if kind == "high" else s["low"]
            want = max(edge[lo:hi]) if kind == "high" else min(edge[lo:hi])
            assert edge[i] == want, (
                f"seed {seed}: {label} {a['label']} on bar {i} is not the {kind} of its swing "
                f"[{lo},{hi}) — {edge[i]} vs {want}"
            )


def test_uptrend_ladder_labels_are_a_rising_staircase() -> None:
    """Each labelled pivot exceeds the previous one of its own kind."""
    config = _config("market_structure", ["uptrend_ladder"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        highs = [s["high"][i] for i in _labelled(annotations, "HH")]
        lows = [s["low"][i] for i in _labelled(annotations, "HL")]
        assert len(highs) >= 3 and len(lows) >= 2, f"seed {seed}: ladder too short to read"
        assert all(b > a for a, b in pairwise(highs)), f"seed {seed}: HH not rising"
        assert all(b > a for a, b in pairwise(lows)), f"seed {seed}: HL not rising"


def test_choch_marker_is_the_first_lower_low() -> None:
    """The marked low is below the previous higher low, and every labelled low before it is still rising."""
    config = _config("market_structure", ["choch_after_uptrend"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        lows = [s["low"][i] for i in _labelled(annotations, "HL")]
        choch = s["low"][_at(annotations, "CHoCH")]
        assert all(b > a for a, b in pairwise(lows)), f"seed {seed}: HL not rising"
        assert choch < lows[-1], f"seed {seed}: CHoCH {choch} is not below the last HL {lows[-1]}"
        assert _at(annotations, "CHoCH") > max(_labelled(annotations, "HH")), (
            f"seed {seed}: the CHoCH must come after the ladder it breaks"
        )


# --- 3. liquidity_sweep (m19-l2, m06-l1): one wick through the shelf, and the reclaim -------------


@pytest.mark.parametrize("label", ["liquidity_sweep", "liquidation_cascade"])
def test_sweep_marker_is_the_bar_that_took_the_pool(label: str) -> None:
    """The marked bar is the window's lowest low, the only one below the shelf, and closes back above."""
    config = _config("liquidity_sweep", [label])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        shelf = _levels(payload)["shelf"]
        w = _at(annotations, "sweep" if label == "liquidity_sweep" else "liquidation")
        assert s["low"][w] == min(s["low"]), f"seed {seed}: the marked bar is not the low of the window"
        assert s["low"][w] < shelf * 0.985, f"seed {seed}: sweep only reached {s['low'][w]} vs {shelf}"
        assert s["close"][w] > shelf, f"seed {seed}: the sweep bar must close back above the shelf"
        below = [i for i, low in enumerate(s["low"]) if low < shelf]
        assert below == [w], f"seed {seed}: bars below the shelf are {below}, expected only {w}"


@pytest.mark.parametrize(("label", "floor"), [("liquidity_sweep", 3.0), ("liquidation_cascade", 5.0)])
def test_sweep_bar_carries_the_volume_of_forced_flow(label: str, floor: float) -> None:
    """The marked bar's volume stands out against its chart, and harder on the cascade."""
    config = _config("liquidity_sweep", [label])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        w = _at(annotations, "sweep" if label == "liquidity_sweep" else "liquidation")
        ratio = s["volume"][w] / float(np.median(s["volume"]))
        assert ratio > floor, f"seed {seed}: {label} sweep volume only {ratio:.1f}x the median"


def test_the_cascade_spikes_harder_than_the_plain_sweep() -> None:
    """The two labels share their geometry and differ only in spike size — asserted, not assumed."""
    sweeps: list[float] = []
    cascades: list[float] = []
    for label, out in (("liquidity_sweep", sweeps), ("liquidation_cascade", cascades)):
        config = _config("liquidity_sweep", [label])
        for seed in range(40):
            _lbl, annotations, payload = _instantiate(config, seed)
            s = _series(payload)
            w = _at(annotations, "sweep" if label == "liquidity_sweep" else "liquidation")
            out.append(s["volume"][w] / float(np.median(s["volume"])))
    assert float(np.mean(cascades)) > 1.4 * float(np.mean(sweeps))


# --- 4. stop_limit_gap (m24-l1): the plan lines the market never came back to ---------------------


def test_one_candle_slices_through_both_order_lines() -> None:
    """One bar crosses both lines — a three-bar drift through the same distance would fill and teach the
    opposite."""
    config = _config("stop_limit_gap", ["unfilled_stop_limit"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        lv = _levels(payload)
        g = _at(annotations, "gap")
        assert lv["limit"] < lv["trigger"], f"seed {seed}: the limit must sit below the trigger"
        assert max(s["open"][g], s["close"][g]) > lv["trigger"], (
            f"seed {seed}: the slice bar must open above the trigger"
        )
        assert min(s["open"][g], s["close"][g]) < lv["limit"], (
            f"seed {seed}: the slice bar must close below the limit — in ONE body"
        )
        assert min(s["close"][:g]) > lv["trigger"], (
            f"seed {seed}: a resting stop cannot have been triggered before the slice"
        )


def test_the_limit_order_never_fills_after_the_gap() -> None:
    """No later bar so much as reaches the limit, wick included.

    A `LevelGuard` cannot carry this: it clamps a breaching wick back TO the line, which would fill.
    """
    config = _config("stop_limit_gap", ["unfilled_stop_limit"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        lv = _levels(payload)
        g, u = _at(annotations, "gap"), _at(annotations, "unfilled")
        assert max(s["high"][g + 1 :]) < lv["limit"], (
            f"seed {seed}: price traded back up to the limit — that is a fill"
        )
        assert u > g, f"seed {seed}: the 'unfilled' marker must come after the gap"
        assert s["high"][u] < lv["limit"], f"seed {seed}: the marked bar must sit below the limit"
        assert s["close"][-1] < s["close"][g], f"seed {seed}: the loss should still be running"


# --- 5. trade_anatomy (m27-l1): the four lines are pinned to the geometry -------------------------


def test_entry_line_is_the_entry_bar_close() -> None:
    """The entry line IS the entry bar's close, not a hair off it."""
    config = _config("trade_anatomy", ["long_setup"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        lv = _levels(payload)
        r = _at(annotations, "rejection")
        assert lv["entry"] == s["close"][r], (
            f"seed {seed}: entry {lv['entry']} is not the rejection bar's close {s['close'][r]}"
        )
        assert s["low"][r] < lv["confluence"] * 0.99, f"seed {seed}: the wick must pierce the level"
        assert s["close"][r] > lv["confluence"], f"seed {seed}: the bar must close back above the level"


def test_stop_line_sits_under_the_deepest_low_and_is_never_hit() -> None:
    """The stop sits just under the rejection wick, which is the setup's deepest low, and is never hit."""
    config = _config("trade_anatomy", ["long_setup"])
    for seed in range(_SEEDS):
        _lbl, annotations, payload = _instantiate(config, seed)
        s = _series(payload)
        lv = _levels(payload)
        r = _at(annotations, "rejection")
        assert s["low"][r] == min(s["low"]), f"seed {seed}: the rejection wick is not the deepest low"
        assert lv["stop"] < min(s["low"]), f"seed {seed}: the stop was traded through"
        assert lv["stop"] > min(s["low"]) * 0.98, (
            f"seed {seed}: the stop is {min(s['low']) / lv['stop']:.3f}x below the wick — too far to be"
            " read off it"
        )


def test_target_line_is_the_prior_high() -> None:
    """The target is exactly the extreme the impulse printed, and far enough above the entry to be a bet."""
    config = _config("trade_anatomy", ["long_setup"])
    for seed in range(_SEEDS):
        _lbl, _ann, payload = _instantiate(config, seed)
        s = _series(payload)
        lv = _levels(payload)
        assert lv["target"] == max(s["high"]), (
            f"seed {seed}: target {lv['target']} is not the prior high {max(s['high'])}"
        )
        reward, risk = lv["target"] - lv["entry"], lv["entry"] - lv["stop"]
        assert reward > 1.5 * risk, f"seed {seed}: target is only {reward / risk:.1f}R away"


def test_the_figure_shows_the_trade_reaching_its_target() -> None:
    """The appended resolution actually reaches the target — a fact about the published frozen seed."""
    panels = build_figure(load_figures(_CONTENT)["fig-m27-trade-anatomy"], "en")["panels"]
    assert isinstance(panels, list)
    p = panels[0]
    s = _series(p)
    lv = _levels(p)
    pre = len(s["close"]) - 24  # the injector's own window, before the appended resolution
    assert max(s["high"][:pre]) == lv["target"], "the prior high should be the pre-resolution extreme"
    assert max(s["high"][pre:]) >= lv["target"], "the resolution never reaches the target"
    assert min(s["low"][pre:]) > lv["stop"], "the resolution must not trade through the stop"
