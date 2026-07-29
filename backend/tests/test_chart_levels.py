# SPDX-License-Identifier: AGPL-3.0-only
"""Drawn-level integrity, for every injector that draws one and every figure that renders one.

A horizontal level is the one annotation a learner *measures against*: m08 asks whether it broke, m09
whether the range held it, m13 which retracement the pullback reached. So a level that renders at a
price the candles do not corroborate does not merely look wrong — it makes the question unanswerable
while the ground truth stays right, which is the worst failure mode available (graded fairly against a
chart that showed something else).

These are statistical tests over hundreds of seeds, because the defect they guard is distributional:
`build_series` draws every wick from a half-normal, so whether a bar touches the line — or randomly
pokes through it — is luck, and any single seed can look fine while most do not. The four invariants:

1. the drawn price IS the injector's planted level, all the way through both render paths;
2. the level is TESTED — the price action reaches it, before the decision and around it;
3. it is only BREACHED where the injector's own `LevelGuard` says it may be;
4. nothing renders as an unlabeled or duplicate line.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns.base import LevelGuard, PatternInjector
from tradeschool.exercises.charts.patterns.common import apply_level_guards
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.charts.types import Series
from tradeschool.exercises.figures import build_figure, load_figures
from tradeschool.exercises.pattern_chart import (
    PatternChartConfig,
    PatternChartGenerator,
    _full,
    _instantiate,
)

_SEEDS = 300  # per injector label — the defect is distributional, so a handful of seeds proves nothing
_N = 130
_KINDS = {"support", "resistance", "fib", "plan"}  # every kind the frontend has a colour and a title for
# A level with a SIDE is a barrier: "beyond" it means broken. A fib level is a measurement grid — price
# travels through it on the way up and that says nothing about it — so the breach rules do not apply.
_BARRIER = {"support", "resistance"}
# Kinds that are claims about where price HAS BEEN, and so must be corroborated by the candles.
#
# A `plan` level is not one of them: an entry, a stop, a target, a stop-limit's trigger and limit are
# prices the TRADER chose. A stop that the price action reached is a stop that got hit, and a target
# price already traded is not a target — so "every drawn level is touched before the decision" is not
# merely inapplicable here, it is the opposite of what those lines claim. They are not exempt from
# scrutiny, they answer to a different and stricter contract: each one is pinned to a specific feature
# of the planted geometry (the entry IS the entry bar's close, the target IS the prior high, the stop
# sits under a rejection wick nothing else trades below, the limit is a line no later bar reaches), and
# `tests/test_chart_annotations.py` is where that is enforced.
_CORROBORATED = _BARRIER | {"fib"}
# Injectors whose chart draws NO corroborated level, only order lines. There is exactly one, and it is
# named here rather than discovered so that an injector which silently stops publishing its
# support/resistance cannot slip through the tests below by looking like this case.
_ORDER_LINE_ONLY = {"stop_limit_gap"}
_CONTENT = Path(__file__).resolve().parents[2] / "content"


def _config(injector: str, targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": n, "targets": targets, "choices": list(get_injector(injector).labels)}
    )


Payload = dict[str, object]


def _levels(payload: Payload) -> list[dict[str, object]]:
    """The generators publish `dict[str, object]`; narrow it here rather than at every use."""
    levels = payload["levels"]
    assert isinstance(levels, list)
    return levels


def _price(level: dict[str, object]) -> float:
    return float(str(level["price"]))


def _hl(payload: Payload) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    s = payload["series"]
    assert isinstance(s, dict)
    return (
        np.asarray(s["high"], dtype=float),
        np.asarray(s["low"], dtype=float),
        np.asarray(s["close"], dtype=float),
    )


def _level_injectors() -> list[tuple[str, str]]:
    """(injector, label) pairs that draw at least one level — discovered, never hard-coded, so a new
    injector is covered the moment it is registered."""
    pairs: list[tuple[str, str]] = []
    for inj in all_injectors():
        for label in inj.labels:
            _lbl, _ann, payload = _instantiate(_config(inj.name, [label]), 0)
            if _levels(payload):
                pairs.append((inj.name, label))
    return pairs


# Collected at import time so pytest can parametrise on it — hence defined after the accessors above.
_LEVEL_PAIRS = _level_injectors()


def _reaches(high: np.ndarray, low: np.ndarray, price: float, kind: str) -> np.ndarray:
    """Bars that traded TO or beyond `price` — the level was engaged, not merely approached."""
    return high >= price if kind == "resistance" else low <= price


def _straddles(high: np.ndarray, low: np.ndarray, price: float) -> np.ndarray:
    return (low <= price) & (high >= price)


def _beyond(values: np.ndarray, price: float, kind: str) -> np.ndarray:
    return values > price if kind == "resistance" else values < price


# --- 1. the drawn price is the planted level -----------------------------------------------------


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_drawn_level_price_is_the_injector_planted_level(injector: str, label: str) -> None:
    """The price on the labelled line equals the level the injector planted, exactly — no rounding
    drift, no reordering, no substituted field. This is the invariant that broke: `candle_reaction`
    used to publish the reaction candle's own wick extreme instead of the level its approach was built
    against, so the line was 3-4% from every bar that was supposed to establish it."""
    config = _config(injector, [label])
    inj = get_injector(injector)
    for seed in range(60):
        planted = inj.build(np.random.default_rng(seed), _N, label)
        _lbl, _ann, payload = _instantiate(config, seed)
        drawn = _levels(payload)
        assert len(drawn) == len(planted.levels), f"seed {seed}: {injector} level count changed"
        for got, want in zip(drawn, planted.levels, strict=True):
            assert got["price"] == want.price, (
                f"seed {seed}: {injector}/{label} drew {got['price']} for planted {want.price}"
            )
            assert got["label"] == want.label and got["kind"] == want.kind


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_exercise_and_full_export_agree_on_every_level(injector: str, label: str) -> None:
    """The graded payload and the dev/full export are two paths over the same generator; a level that
    differs between them means one of the two is reading the wrong object."""
    config = _config(injector, [label])
    for seed in range(40):
        _lbl, _ann, payload = _instantiate(config, seed)
        full = _full(config, seed)
        assert _levels(payload) == full.levels, f"seed {seed}: {injector} level mismatch"


# --- 2. the level is tested by the price action --------------------------------------------------


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_every_drawn_level_is_tested_before_the_decision(injector: str, label: str) -> None:
    """A line price never went to is not a level. Every drawn level must be straddled by candles in the
    range that precedes the decision — those prior touches are the entire reason a learner can believe
    the line. Before this was enforced, `fakeout`, `volume_confirmation`, `candle_reaction` and a plain
    `wyckoff` range drew levels with ZERO pre-decision touches in 100% of seeds.

    A barrier needs at least TWO touches, and they must be SEPARATED. One touch is a coincidence, and
    two adjacent bars grazing the line are one touch — which is exactly the hole the first version of
    this test left open: it asserted `.any()`, so a level brushed by two lone planted wicks 1.5% from
    every candle body passed while still reading as a line in empty space (m14-ex-1/ex-2 review).
    A fib level needs only one: it is a measurement grid the pullback lands on, not a barrier. A `plan`
    level is out of scope entirely — see `_CORROBORATED`."""
    config = _config(injector, [label])
    for seed in range(_SEEDS):
        _lbl, _ann, payload = _instantiate(config, seed)
        high, low, _close = _hl(payload)
        decision = int(0.76 * len(high))
        for lvl in _levels(payload):
            price, kind = _price(lvl), str(lvl["kind"])
            if kind not in _CORROBORATED:
                continue
            touched = np.flatnonzero(_straddles(high[:decision], low[:decision], price))
            assert touched.size, (
                f"seed {seed}: {injector}/{label} draws {kind} at {price} that no candle "
                f"reaches before the decision"
            )
            if kind not in _BARRIER:
                continue
            assert touched.size >= 2, (
                f"seed {seed}: {injector}/{label} {kind} at {price} touched by only "
                f"{touched.size} bar(s) before the decision"
            )
            # Two touches >5 bars apart: price left the level and came back to it.
            assert int(touched[-1] - touched[0]) > 5, (
                f"seed {seed}: {injector}/{label} {kind} at {price} touched only at bars "
                f"{touched.tolist()} — one visit, not a level price keeps returning to"
            )


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_the_decision_engages_a_drawn_level(injector: str, label: str) -> None:
    """The event the exercise asks about happens AT a drawn level: somewhere in the decision region a
    candle must trade to or through one. A test that stops short of the line is not a test of it.

    Only corroborated kinds count towards it — a chart whose sole engaged line was the trader's own
    stop would satisfy the letter of this and none of its point. A chart with no corroborated line at
    all has no subject here, and `_ORDER_LINE_ONLY` pins which chart that is allowed to be."""
    config = _config(injector, [label])
    _l0, _a0, first = _instantiate(config, 0)
    if not [lvl for lvl in _levels(first) if str(lvl["kind"]) in _CORROBORATED]:
        assert injector in _ORDER_LINE_ONLY, (
            f"{injector}/{label} draws only order lines — did it stop publishing its market level?"
        )
        return
    for seed in range(_SEEDS):
        _lbl, _ann, payload = _instantiate(config, seed)
        high, low, _close = _hl(payload)
        # The last third: every injector's decision (a break, a spring, a pullback extreme, a reaction
        # candle) lives there. A plain range has no single decision — it tests its bounds throughout —
        # so the window is wide enough to catch its late swing rather than one designated bar.
        tail = slice(int(0.66 * len(high)), len(high))
        engaged = any(
            _reaches(high[tail], low[tail], _price(lvl), str(lvl["kind"])).any()
            for lvl in _levels(payload)
            if str(lvl["kind"]) in _CORROBORATED
        )
        assert engaged, f"seed {seed}: {injector}/{label} decision never reaches a drawn level"


# --- 3. a level is only breached where its own guard allows --------------------------------------


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_barrier_levels_declare_a_guard(injector: str, label: str) -> None:
    """A support/resistance is a claim about where price did NOT go, so it must ship the candle-space
    contract that makes the claim true (see `LevelGuard`). Without one, `build_series`' random wicks
    decide — which is how `no_break` came to print a wick through its own level in 56% of seeds."""
    result = get_injector(injector).build(np.random.default_rng(0), _N, label)
    barriers = [lv for lv in result.levels if lv.kind in _BARRIER]
    if not barriers:
        return
    guarded = {g.price for g in result.level_guards}
    missing = [lv.price for lv in barriers if lv.price not in guarded]
    assert not missing, f"{injector}/{label}: barrier levels without a LevelGuard: {missing}"


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_level_is_never_breached_inside_its_guarded_span(injector: str, label: str) -> None:
    """Inside a `no_breach` span nothing trades beyond the level — wick included. The bodies are
    checked too: the guard only moves wicks, so a close on the wrong side is a shape bug it cannot fix
    and must surface here rather than be papered over."""
    config = _config(injector, [label])
    inj = get_injector(injector)
    for seed in range(_SEEDS):
        guards = inj.build(np.random.default_rng(seed), _N, label).level_guards
        _lbl, _ann, payload = _instantiate(config, seed)
        high, low, close = _hl(payload)
        warmup = _full(config, seed).warmup
        for g in guards:
            edge = high if g.kind == "resistance" else low
            for lo, hi in g.no_breach:
                # Guard spans are full-series coords; the payload starts after the warm-up.
                a, b = max(0, lo - warmup), min(hi - warmup, len(high))
                if a >= b:
                    continue
                assert not _beyond(edge[a:b], g.price, g.kind).any(), (
                    f"seed {seed}: {injector}/{label} wick beyond {g.kind} {g.price} in [{a},{b})"
                )
                assert not _beyond(close[a:b], g.price, g.kind).any(), (
                    f"seed {seed}: {injector}/{label} CLOSE beyond {g.kind} {g.price} in [{a},{b})"
                )


def test_no_break_never_trades_beyond_its_level() -> None:
    """m08-ex-2 asks the learner to separate `false_break` from `no_break`, so the difference has to be
    on screen and nowhere else: a no-break chart must not breach the level at all, and a false break
    must both close beyond it and end back inside."""
    labels = ["genuine_breakout", "false_break", "no_break"]
    config = _config("fakeout", labels)
    seen = dict.fromkeys(labels, 0)
    for seed in range(600):
        label, _ann, payload = _instantiate(config, seed)
        seen[label] += 1
        lvl = _levels(payload)[0]
        price, kind = _price(lvl), str(lvl["kind"])
        high, low, close = _hl(payload)
        edge = high if kind == "resistance" else low
        ever_closed_beyond = bool(_beyond(close, price, kind).any())
        settled = float(np.median(close[int(0.90 * len(close)) : len(close) - 8]))
        settled_beyond = bool(_beyond(np.array([settled]), price, kind)[0])
        if label == "no_break":
            assert not _beyond(edge, price, kind).any(), f"seed {seed}: no_break breached by a wick"
            assert not ever_closed_beyond, f"seed {seed}: no_break closed beyond the level"
        elif label == "false_break":
            assert ever_closed_beyond, f"seed {seed}: false_break never closed beyond the level"
            assert not settled_beyond, f"seed {seed}: false_break settled beyond the level"
        else:
            assert settled_beyond, f"seed {seed}: genuine_breakout did not settle beyond the level"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


def test_fakeout_holds_every_label_the_same_distance_from_the_level() -> None:
    """The side price holds on and whether it poked through are the answer; how FAR the right edge sits
    from the line must not be, or the label is readable off a ruler instead of the structure."""
    config = _config("fakeout", ["genuine_breakout", "false_break", "no_break"])
    dist: dict[str, list[float]] = {}
    for seed in range(400):
        label, _ann, payload = _instantiate(config, seed)
        price = _price(_levels(payload)[0])
        _high, _low, close = _hl(payload)
        settled = float(np.median(close[int(0.90 * len(close)) : len(close) - 8]))
        dist.setdefault(label, []).append(abs(settled - price) / price)
    means = {k: float(np.mean(v)) for k, v in dist.items()}
    spread = max(means.values()) - min(means.values())
    assert spread < 0.01, f"hold distance leaks the label: {means}"


# --- 4. nothing renders as an unlabeled or duplicate line ----------------------------------------


@pytest.mark.parametrize(("injector", "label"), _LEVEL_PAIRS)
def test_no_orphan_or_duplicate_level_lines(injector: str, label: str) -> None:
    """Every rendered horizontal line must be a level the injector planted, carry a title, and sit at
    its own price. Two lines at one price render as one; a level with no label renders as an untitled
    dashed line the learner reads as a mystery second level — which is exactly what the chart
    component's default last-close price line looked like before it was switched off."""
    config = _config(injector, [label])
    for seed in range(_SEEDS):
        _lbl, _ann, payload = _instantiate(config, seed)
        levels = _levels(payload)
        prices = [_price(lv) for lv in levels]
        assert len(set(prices)) == len(prices), f"seed {seed}: {injector} duplicate level prices"
        for lv in levels:
            assert str(lv["label"]), f"seed {seed}: {injector} level with no label would render bare"
            assert str(lv["kind"]) in _KINDS, f"seed {seed}: {injector} unknown level kind {lv['kind']}"


# --- the shared enforcement helper itself --------------------------------------------------------


def _series(highs: list[float], lows: list[float], closes: list[float]) -> Series:
    opens = [closes[0], *closes[:-1]]
    return Series(
        time=list(range(len(closes))), open=opens, high=highs, low=lows, close=closes,
        volume=[1.0] * len(closes),
    )


def test_level_guard_extends_a_test_wick_to_the_level() -> None:
    s = _series(highs=[100.0, 101.0], lows=[98.0, 99.0], closes=[99.5, 100.5])
    apply_level_guards(s, [LevelGuard(price=104.0, kind="resistance", tests=(1,))])
    assert s.high[0] == 100.0, "an unguarded bar must be left alone"
    assert s.high[1] >= 104.0, "a test bar's wick must reach the level"


def test_level_guard_clamps_a_breaching_wick_but_never_a_body() -> None:
    s = _series(highs=[110.0, 110.0], lows=[98.0, 99.0], closes=[99.5, 106.0])
    apply_level_guards(s, [LevelGuard(price=104.0, kind="resistance", no_breach=((0, 2),))])
    assert s.high[0] == 104.0, "a breaching wick is clamped back to the level"
    # Bar 1 CLOSES beyond the level: the guard may not move a body, so the breach stays visible for
    # `test_level_is_never_breached_inside_its_guarded_span` to fail on.
    assert s.high[1] == 106.0, "the guard must not clamp a high below the bar's own body"


def test_level_guard_leaves_a_tested_unbreakable_level_touching_exactly() -> None:
    """A bar that both tests a level and sits in a no-breach span tops out ON it — a tested-but-held
    level, which is what `no_break`'s decision candle has to look like."""
    s = _series(highs=[100.0], lows=[98.0], closes=[99.5])
    guard = LevelGuard(price=104.0, kind="resistance", tests=(0,), no_breach=((0, 1),))
    apply_level_guards(s, [guard])
    assert s.high[0] == 104.0


def test_level_guard_mirrors_for_support() -> None:
    s = _series(highs=[110.0, 110.0], lows=[90.0, 108.0], closes=[105.0, 109.0])
    apply_level_guards(s, [LevelGuard(price=100.0, kind="support", tests=(1,), no_breach=((0, 1),))])
    assert s.low[0] == 100.0, "a support breach is clamped up to the level"
    assert s.low[1] <= 100.0, "a support test wick reaches down to the level"


# --- figures render the same corroborated levels -------------------------------------------------


def _panels(figure_id: str) -> list[Payload]:
    data = build_figure(load_figures(_CONTENT)[figure_id], "en")
    panels = data["panels"]
    assert isinstance(panels, list)
    return panels


def _figure_panels() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for fid, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        out += [(fid, i) for i, panel in enumerate(_panels(fid)) if _levels(panel)]
    return out


@pytest.mark.parametrize(("figure_id", "panel"), _figure_panels())
def test_figure_levels_are_tested_by_the_pre_resolution_action(figure_id: str, panel: int) -> None:
    """Figures run the same injectors through the same `Level`/`LevelGuard` contract, then append the
    resolution an exercise cuts off. The resolution legitimately walks away from the level — that IS
    the lesson — so what must hold is that the action BEFORE it tested the line.

    `plan` levels are out of scope here for the reason given at `_CORROBORATED`: the resolution is
    precisely where a target gets reached and where a stop proves it was never hit."""
    p = _panels(figure_id)[panel]
    high, low, _close = _hl(p)
    # The injector's own window, before `_RESOLUTION_CANDLES` of appended continuation.
    pre = len(high) - 24
    for lvl in _levels(p):
        price = _price(lvl)
        assert str(lvl["label"]), f"{figure_id} panel{panel}: level with no label renders bare"
        if str(lvl["kind"]) not in _CORROBORATED:
            continue
        assert _straddles(high[:pre], low[:pre], price).any(), (
            f"{figure_id} panel{panel}: {lvl['kind']} at {price} is never reached before the resolution"
        )


def test_no_two_figures_draw_the_same_level_price() -> None:
    """Two different figures labelling a line with the SAME price to the cent reads as a bug, and is
    one: every injector picks its base price from the same five-tier table with the same two opening
    draws, so two figures on one seed get an identical base — and the m17/m21/m24 injectors each draw
    their level AT that base, which put `2016.67` on three charts in three different modules.

    A figure's seed is frozen content, so the fix is a seed per tier, and this is what keeps it fixed:
    the next figure built on one of these injectors either picks a fresh tier or fails here.

    Panels WITHIN one figure are exempt: a two-panel comparison deliberately shares a scale (m08's two
    ladders are the same chart until the last swing), and there the repetition is the point."""
    by_price: dict[float, list[str]] = {}
    for figure_id, panel in _figure_panels():
        for lvl in _levels(_panels(figure_id)[panel]):
            by_price.setdefault(_price(lvl), []).append(f"{figure_id}:{lvl['label']}")
    shared = {
        price: where
        for price, where in by_price.items()
        if len({w.split(":")[0] for w in where}) > 1
    }
    assert not shared, f"the same level price drawn by different figures: {shared}"


def test_every_injector_that_draws_a_level_is_covered() -> None:
    """The parametrised suites above discover their own targets; this fails if that discovery silently
    finds nothing (a refactor that stops publishing levels would otherwise make the file vacuous)."""
    drawn = {name for name, _label in _LEVEL_PAIRS}
    assert drawn >= {
        "fakeout", "volume_confirmation", "wyckoff", "fibonacci", "candle_reaction",
        # ...and the figure injectors that draw lines: the m24 trade's four, the m17/m06 shelf, and the
        # m21 order pair (whose `plan` kinds still owe the discovered price/guard/no-orphan checks).
        "trade_anatomy", "liquidity_sweep", "stop_limit_gap",
    }
    assert _figure_panels(), "no figure exposes a level — level rendering lost its figure coverage"


def test_injector_contract_is_typed_as_expected() -> None:
    """`level_guards` is part of the injector contract, not an optional extra a new injector can miss
    seeing: it lives on `PatternResult` next to `levels`."""
    assert hasattr(PatternInjector, "build")
    result = get_injector("fakeout").build(np.random.default_rng(0), _N, "no_break")
    assert result.level_guards and isinstance(result.level_guards[0], LevelGuard)
