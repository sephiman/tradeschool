# SPDX-License-Identifier: AGPL-3.0-only
"""Drawn-DIAGONAL integrity (m31), for every injector that draws one and every figure that renders one.

The moving-level twin of `test_chart_levels.py`, and it needs its own file for the reason the diagonal
needs its own primitive: a horizontal level is enforced by moving wicks (`LevelGuard`), and a diagonal
cannot be — a wick through a trendline is the ordinary case m31-l1 teaches you to ignore, so repairing
it would enforce the opposite of the lesson. The contract is therefore ASSERTED on the CLOSES over
hundreds of seeds, the way a `Band`'s is.

Six sections: §1 what every drawn diagonal owes; §2 the respect contract and the MEASURED floors its
two margins were set from; §3 that those margins are load-bearing rather than decorative; §4 the labels
of `trend_channel`; §5 the convergence `converging_lines` claims; §6 the figures.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns import diagonals as dg
from tradeschool.exercises.charts.patterns.base import Diagonal, PatternResult
from tradeschool.exercises.charts.patterns.converging_lines import _SHAPE_LABELS, _SWING_F
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.charts.patterns.trend_channel import _PRE_DECIDE, _TOUCH_F
from tradeschool.exercises.charts.types import Series
from tradeschool.exercises.figures import build_figure, load_figures
from tradeschool.exercises.pattern_chart import (
    PatternChartConfig,
    PatternChartGenerator,
    _full,
    _instantiate,
)

_SEEDS = 300  # the noise that decides whether a visit lands on the line is a draw, per bar
_N = 130
_KINDS = {"support", "resistance"}  # a diagonal always has an inside; there is no `fib` case
_CONTENT = Path(__file__).resolve().parents[2] / "content"
#: Injectors that draw a diagonal. Named as well as discovered, so one that silently STOPS drawing
#: cannot make every parametrised suite below vacuous by looking like it never did.
_DIAGONAL_INJECTORS = {"trend_channel", "converging_lines"}
_RESOLUTION_CANDLES = 24  # what a figure appends; mirrors `figures._RESOLUTION_CANDLES`

Payload = dict[str, object]


def _config(injector: str, targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": n, "targets": targets, "choices": list(get_injector(injector).labels)}
    )


def _diagonal_labels() -> list[tuple[str, str]]:
    """(injector, label) pairs that draw a diagonal, discovered so a new one is covered on sight."""
    out: list[tuple[str, str]] = []
    for inj in all_injectors():
        for label in inj.labels:
            if inj.build(np.random.default_rng(0), _N, label).diagonals:
                out.append((inj.name, label))
    return out


_DIAGONAL_PAIRS = _diagonal_labels()


def _drawn(payload: Payload) -> list[dict[str, object]]:
    raw = payload.get("diagonals", [])
    assert isinstance(raw, list)
    return raw


def _window(result: PatternResult, n: int, warmup: int) -> tuple[int, int]:
    """The bars the rhythm owns: from the line's first anchor to just before the decision."""
    return result.diagonals[0].start, warmup + int(_PRE_DECIDE * n)


# --- 1. what every drawn diagonal owes ------------------------------------------------------------


@pytest.mark.parametrize(("injector", "label"), _DIAGONAL_PAIRS)
def test_every_drawn_diagonal_is_renderable(injector: str, label: str) -> None:
    """Placeable, titled, of a known kind, inside the visible window, and at prices on screen."""
    config = _config(injector, [label])
    for seed in range(60):
        _lbl, _ann, payload = _instantiate(config, seed)
        s = payload["series"]
        assert isinstance(s, dict)
        n = len(s["close"])
        low, high = min(s["low"]), max(s["high"])
        seen: set[tuple[float, float]] = set()
        for d in _drawn(payload):
            start, end = int(str(d["start"])), int(str(d["end"]))
            p0, p1 = float(str(d["start_price"])), float(str(d["end_price"]))
            assert 0 <= start < end < n, f"seed {seed}: {injector}/{label} anchors [{start},{end}]"
            assert str(d["label"]), f"seed {seed}: {injector}/{label} diagonal with no label renders bare"
            assert str(d["kind"]) in _KINDS, f"seed {seed}: unknown diagonal kind {d['kind']!r}"
            # The START anchor is a designed visit, so it sits among the candles — that is the claim
            # worth asserting, and it is the one a misplaced line breaks.
            assert low <= p0 <= high, (
                f"seed {seed}: {injector}/{label} anchors {d['label']} at {p0}, outside the rendered "
                f"range [{low}, {high}] — a line nobody can see is not a line"
            )
            # The FAR end is deliberately NOT held inside it. A projection is only useful past the bars
            # that drew it: a `line_break` chart ends 4.5% below its own trendline by construction, so
            # demanding the line stay within the candles would be demanding it stop where the question
            # starts. What it may not do is wander off the price scale entirely.
            assert 0.75 * low <= p1 <= 1.25 * high, (
                f"seed {seed}: {injector}/{label} line [{p0}, {p1}] runs off the price scale"
            )
            assert (p0, p1) not in seen, f"seed {seed}: {injector}/{label} duplicate diagonal"
            seen.add((p0, p1))


@pytest.mark.parametrize(("injector", "label"), _DIAGONAL_PAIRS)
def test_exercise_and_full_export_agree_on_every_diagonal(injector: str, label: str) -> None:
    """The graded payload and the dev/full export agree — two paths over the same generator."""
    config = _config(injector, [label])
    for seed in range(40):
        _lbl, _ann, payload = _instantiate(config, seed)
        assert _drawn(payload) == _full(config, seed).diagonals, f"seed {seed}: {injector} mismatch"


def test_a_diagonal_is_public_where_a_band_is_withheld() -> None:
    """The asymmetry stated once: the zone IS the answer (m30), the line is the QUESTION (m31)."""
    for injector, label in _DIAGONAL_PAIRS[:1] + _DIAGONAL_PAIRS[-1:]:
        _lbl, _ann, payload = _instantiate(_config(injector, [label]), 0)
        assert _drawn(payload), f"{injector}/{label} withheld the line its own question is asked about"
        assert "bands" not in payload


def test_every_injector_that_draws_a_diagonal_is_covered() -> None:
    """Fails if the parametrised suites' discovery silently finds nothing."""
    assert {name for name, _label in _DIAGONAL_PAIRS} == _DIAGONAL_INJECTORS
    assert _figure_diagonal_panels(), "no figure renders a diagonal — it lost its figure coverage"


def test_diagonal_is_part_of_the_injector_contract() -> None:
    """`diagonals` lives on `PatternResult` next to `levels`, not as an optional extra."""
    result = get_injector("trend_channel").build(np.random.default_rng(0), _N, "line_break")
    assert isinstance(result, PatternResult)
    assert result.diagonals and isinstance(result.diagonals[0], Diagonal)
    assert PatternResult(close_full=result.close_full, warmup=0, label="x").diagonals == []


# --- 2. the respect contract, and the floors its margins were measured from -----------------------


@pytest.mark.parametrize(("injector", "label"), _DIAGONAL_PAIRS)
def test_every_drawn_diagonal_is_validated_before_the_decision(injector: str, label: str) -> None:
    """Three separated touches and no close through it: `diagonals.respected`, the whole contract.

    Two touches define a candidate line and the THIRD validates it (m31-l1), so a chart that draws one
    with two is a chart teaching the discipline it just broke.
    """
    inj = get_injector(injector)
    for seed in range(_SEEDS):
        result = inj.build(np.random.default_rng(seed), _N, label)
        f = _full(_config(injector, [label]), seed)
        lo, hi = _window(result, _N, f.warmup)
        for d in result.diagonals:
            lo = max(lo, d.start)
            found = dg.touches(f.series, d, d.start, hi)
            assert len(found) >= 3, (
                f"seed {seed}: {injector}/{label} draws {d.label!r} with {len(found)} touch(es) at "
                f"{found} — two make a candidate line, the third is what validates it"
            )
            breach = dg.worst_breach(f.series, d, d.start, hi)
            assert breach <= dg.BREACH_MARGIN, (
                f"seed {seed}: {injector}/{label} closes {breach:+.3%} through {d.label!r} before the "
                f"decision — the rhythm the line claims was already over"
            )
            assert dg.respected(f.series, d, d.start, hi)


def test_the_measured_floor_the_touch_margin_was_set_from() -> None:
    """Re-measure, never trust: the closest bar of a designed visit against `TOUCH_MARGIN`.

    The margin is a *measured* bound, the discipline m30's 2%-against-a-3.40%-floor established. This
    recomputes the floor on every run, so an injector edit that drifts the visits away from the line
    fails here with the number rather than silently spending the headroom.
    """
    worst, samples = 0.0, 0
    inj = get_injector("trend_channel")
    for label in inj.labels:
        config = _config("trend_channel", [label])
        for seed in range(120):
            result = inj.build(np.random.default_rng(seed), _N, label)
            f = _full(config, seed)
            for d, fracs in zip(result.diagonals, (_TOUCH_F, (0.18, 0.42, 0.63)), strict=False):
                for fr in fracs:
                    a, b = f.warmup + int((fr - 0.018) * _N), f.warmup + int((fr + 0.018) * _N) + 1
                    line = dg.projected(d, a, b)
                    close = np.asarray(f.series.close[a:b], dtype=float)
                    worst = max(worst, float(np.min(np.abs((close - line) / line))))
                    samples += 1
    assert samples > 2000, "the floor sweep stopped sampling"
    assert worst <= dg.TOUCH_MARGIN, (
        f"a designed visit now lands {worst:.3%} from its line, past the {dg.TOUCH_MARGIN:.1%} margin"
    )
    assert worst < 0.8 * dg.TOUCH_MARGIN, (
        f"the worst designed visit is {worst:.3%}, only {dg.TOUCH_MARGIN / worst:.2f}x inside the "
        f"margin — the bound has stopped being a bound and is now tracing the output"
    )


def test_the_margins_are_load_bearing_and_not_decoration() -> None:
    """Red-first, in code: tighten each margin past its measured floor and the contract must fail.

    Without this a margin wide enough to accept anything would pass every test above forever.
    """
    inj = get_injector("trend_channel")
    result = inj.build(np.random.default_rng(0), _N, "line_holds")
    f = _full(_config("trend_channel", ["line_holds"]), 0)
    lo, hi = _window(result, _N, f.warmup)
    d = result.diagonals[0]
    assert dg.respected(f.series, d, lo, hi)
    # A pencil thin enough and the validated line has no touches left.
    assert len(dg.touches(f.series, d, lo, hi, margin=0.0001)) < 3
    # ...and a line moved bodily through the price action is not respected at any margin.
    through = Diagonal(
        start=d.start, end=d.end,
        start_price=d.start_price * 1.03, end_price=d.end_price * 1.03,
        label=d.label, kind=d.kind,
    )
    assert not dg.respected(f.series, through, lo, hi)


def test_touches_count_visits_and_not_bars() -> None:
    """A five-bar plateau is ONE touch. Counting bars is how a line price never left certifies itself."""
    from tradeschool.exercises.charts.types import Series

    closes = [100.0] * 6 + [110.0] * 20 + [100.0] * 6
    series = Series(
        time=list(range(len(closes))), open=list(closes), high=list(closes), low=list(closes),
        close=closes, volume=[1.0] * len(closes),
    )
    flat = Diagonal(start=0, end=len(closes) - 1, start_price=100.0, end_price=100.0, kind="support")
    assert dg.touches(series, flat, 0, len(closes)) == [0, 26]


# --- 3. `trend_channel`: the labels, and that none of them is readable off a ruler ----------------


#: Which drawn line each label's decision happens at. A channel has two, and WHICH of them price left
#: through is the difference between an acceleration and the rhythm giving out — so `channel_failed`
#: decides at the anchor, exactly like the single-line labels, not at the parallel.
_DECIDES_AT_PARALLEL = {"channel_intact", "channel_broken"}


def _decided(result: PatternResult, label: str) -> Diagonal:
    """The line the label is about: the parallel for the two that end there, the anchor otherwise."""
    return result.diagonals[-1] if label in _DECIDES_AT_PARALLEL else result.diagonals[0]


@pytest.mark.parametrize(
    ("label", "settles_beyond"),
    [("line_holds", False), ("line_break", True), ("line_fakeout", False),
     ("channel_intact", False), ("channel_broken", True), ("channel_failed", True)],
)
def test_trend_channel_settles_on_the_side_its_label_claims(label: str, settles_beyond: bool) -> None:
    """Where the chart ENDS up is the answer: through the line, or back on the inside of it."""
    inj = get_injector("trend_channel")
    config = _config("trend_channel", [label])
    for seed in range(_SEEDS):
        result = inj.build(np.random.default_rng(seed), _N, label)
        f = _full(config, seed)
        d = _decided(result, label)
        a, b = f.warmup + int(0.90 * _N), f.warmup + _N - 8
        settled = float(np.median(np.asarray(f.series.close[a:b], dtype=float)))
        line = dg.price_at(d, (a + b) // 2)
        beyond = (settled > line) if d.kind == "resistance" else (settled < line)
        assert beyond == settles_beyond, (
            f"seed {seed}: {label} settles at {settled:.2f} against a line at {line:.2f} — "
            f"{'inside' if not beyond else 'beyond'} it, which is the other label's picture"
        )


def test_a_fakeout_closes_through_the_line_and_a_hold_never_does() -> None:
    """The distinction the whole trio exists for, on the BODY — a wick through a diagonal is nothing."""
    inj = get_injector("trend_channel")
    for label, must_close_through in (("line_holds", False), ("line_fakeout", True),
                                      ("line_break", True), ("channel_intact", False),
                                      ("channel_broken", True), ("channel_failed", True)):
        config = _config("trend_channel", [label])
        for seed in range(_SEEDS):
            result = inj.build(np.random.default_rng(seed), _N, label)
            f = _full(config, seed)
            d = _decided(result, label)
            lo = d.start
            through = dg.worst_breach(f.series, d, lo, len(f.series.close)) > dg.BREACH_MARGIN
            assert through == must_close_through, (
                f"seed {seed}: {label} {'never closed through' if not through else 'closed through'} "
                f"its line, which contradicts the label"
            )


def test_every_trend_channel_label_settles_the_same_distance_from_its_line() -> None:
    """The SIDE is the answer; the distance must not be, or the chart is solvable with a ruler.

    m08's fakeout owes its level the identical promise (`test_chart_levels.py`); this is that test with
    the level in motion.
    """
    inj = get_injector("trend_channel")
    dist: dict[str, list[float]] = {}
    for label in inj.labels:
        config = _config("trend_channel", [label])
        for seed in range(200):
            result = inj.build(np.random.default_rng(seed), _N, label)
            f = _full(config, seed)
            d = _decided(result, label)
            a, b = f.warmup + int(0.90 * _N), f.warmup + _N - 8
            close = np.asarray(f.series.close[a:b], dtype=float)
            line = dg.projected(d, a, b)
            dist.setdefault(label, []).append(float(np.median(np.abs(close - line) / line)))
    means = {k: float(np.mean(v)) for k, v in dist.items()}
    spread = max(means.values()) - min(means.values())
    assert spread < 0.01, f"the settle distance leaks the label: {means}"


def test_the_break_brings_participation_and_the_fakeout_does_not() -> None:
    """m31-l1 reads a diagonal break with m14's rule, so the generated volume has to agree with it."""
    inj = get_injector("trend_channel")
    ratios: dict[str, list[float]] = {}
    for label in ("line_break", "line_fakeout", "line_holds"):
        for seed in range(150):
            result = inj.build(np.random.default_rng(seed), _N, label)
            volume = result.volume_full
            assert volume is not None
            w = result.warmup
            window = volume[w + int(0.78 * _N) : w + int(0.86 * _N)]
            baseline = volume[w : w + int(0.70 * _N)]
            ratios.setdefault(label, []).append(float(np.median(window) / np.median(baseline)))
    assert float(np.mean(ratios["line_break"])) > 2.0, "a genuine break arrived on nobody's volume"
    assert float(np.mean(ratios["line_fakeout"])) < 0.9, "the fakeout arrived on a crowd"
    assert 0.9 < float(np.mean(ratios["line_holds"])) < 1.3, "a hold should carry ordinary volume"


# --- 4. the DIRECTIONALITY exception, stated where the guard it excepts can be read ---------------
#
# `test_chart_bands.py` §3b pins the m30 injectors to the bullish case, and says why: m30-ex-1 and
# m30-ex-2 describe that geometry IN WORDS, so a bearish seed would be graded against a question
# describing the mirror of what is on screen.
#
# The m31 family is the NAMED EXCEPTION to that guard, and it is an exception because the reason does
# not apply rather than because the rule was inconvenient: its prompts and its prose say "the line" and
# "beyond it", never "the high", so a falling channel answers the same question a rising one does.
# These two tests are the other side of that deal — they fail if the family ever stops shipping both
# directions, which is exactly when those prompts would quietly become half wrong.


def test_the_diagonal_family_ships_both_directions() -> None:
    """Bidirectional from birth: over a seed sweep every `trend_channel` label draws its line both ways.

    `converging_lines` is checked below instead, because its two lines are a ceiling and a floor rather
    than a direction — a shape there names its own bias, and its direction is the midline's.
    """
    inj = get_injector("trend_channel")
    for label in inj.labels:
        kinds = {
            inj.build(np.random.default_rng(seed), _N, label).diagonals[0].kind for seed in range(80)
        }
        assert kinds == _KINDS, (
            f"trend_channel/{label} only ever draws a {kinds} line. This family is the documented "
            f"exception to the bull-only guard in test_chart_bands.py §3b — it is bidirectional "
            f"because its prompts are symmetric, and a one-sided generator quietly ends that."
        )


def test_the_coil_family_drifts_both_ways_too() -> None:
    """A wedge points where it drifts, so the resolution family — which picks its own shape — must
    draw both an upward and a downward coil, and the control must too."""
    inj = get_injector("converging_lines")
    for label in ("break_confirmed", "break_unconfirmed", "compression_holding", "parallel_channel"):
        drifts = set()
        for seed in range(80):
            upper, lower = inj.build(np.random.default_rng(seed), _N, label).diagonals
            mid0 = (upper.start_price + lower.start_price) / 2
            mid1 = (upper.end_price + lower.end_price) / 2
            drifts.add(mid1 > mid0)
        assert drifts == {True, False}, f"converging_lines/{label} only ever drifts one way"


def test_both_directions_pass_the_respect_contract() -> None:
    """...and the contract holds in both, which is the half that makes the exception safe to have."""
    inj = get_injector("trend_channel")
    checked = {"support": 0, "resistance": 0}
    for label in inj.labels:
        config = _config("trend_channel", [label])
        for seed in range(120):
            result = inj.build(np.random.default_rng(seed), _N, label)
            f = _full(config, seed)
            lo, hi = _window(result, _N, f.warmup)
            for d in result.diagonals:
                assert dg.respected(f.series, d, lo, hi), f"seed {seed}: {label} {d.kind} not respected"
            checked[result.diagonals[0].kind] += 1
    assert min(checked.values()) > 100, f"one direction is barely sampled: {checked}"


# --- 5. `converging_lines`: the convergence is asserted, not merely tuned -------------------------


@pytest.mark.parametrize("label", [*_SHAPE_LABELS, "break_confirmed", "compression_holding"])
def test_the_lines_converge_monotonically_except_for_the_control(label: str) -> None:
    """The inter-line span shrinks bar by bar and ends a real fraction of where it started.

    `parallel_channel` is the control and must do neither — without it "converging" is a claim no chart
    could fail, which is the same reason `no_imbalance` exists.
    """
    inj = get_injector("converging_lines")
    for seed in range(120):
        result = inj.build(np.random.default_rng(seed), _N, label)
        upper, lower = result.diagonals
        span = np.array([
            dg.price_at(upper, i) - dg.price_at(lower, i)
            for i in range(upper.start, upper.end + 1)
        ])
        assert float(span.min()) > 0, f"seed {seed}: {label} lines crossed"
        ratio = float(span[-1] / span[0])
        if label == "parallel_channel":
            assert 0.97 < ratio < 1.03, f"seed {seed}: the control converged to {ratio:.2f}"
            continue
        assert float(np.max(np.diff(span))) <= 1e-6, f"seed {seed}: {label} span widened somewhere"
        assert ratio < 0.55, f"seed {seed}: {label} only closed to {ratio:.2f} of its opening width"


def _bar_range_ratio(label: str, seeds: int = 120) -> float:
    """Mean closing bar range over mean opening bar range, both relative to price."""
    inj = get_injector("converging_lines")
    config = _config("converging_lines", [label])
    ratios = []
    for seed in range(seeds):
        f = _full(config, seed)
        lo = inj.build(np.random.default_rng(seed), _N, label).diagonals[0].start
        high = np.asarray(f.series.high[lo:], dtype=float)
        low = np.asarray(f.series.low[lo:], dtype=float)
        early = float(np.mean((high - low)[:30] / low[:30]))
        late = float(np.mean((high - low)[-30:] / low[-30:]))
        ratios.append(late / early)
    return float(np.mean(ratios))


@pytest.mark.parametrize("label", [s for s in _SHAPE_LABELS if s != "parallel_channel"])
def test_the_candles_narrow_with_the_lines(label: str) -> None:
    """"Each bar's range narrows" (m31-l2) is a claim about the CANDLES, so it is checked on them.

    The lines are linear by construction, so their own convergence is arithmetic and the test above is
    nearly a tautology. This is the half that can actually be false, and was: at the original width the
    coil's closing bars measured 1.03x its opening ones.
    """
    ratio = _bar_range_ratio(label)
    assert ratio < 0.55, f"{label}'s bars only narrowed to {ratio:.2f} of their opening range"


def test_a_coil_narrows_measurably_more_than_the_control() -> None:
    """The comparative claim, which is the one that isolates convergence from cadence.

    The control's bars narrow somewhat too (~0.65), and not because it is secretly coiling: its swings
    are evenly spaced in TIME while the window's last stretch carries fewer of them, so the closing bars
    move less whatever the lines do. Reading the absolute number alone would credit that artefact to a
    convergence the control does not have — so the shapes are also required to beat it by a margin.
    """
    control = _bar_range_ratio("parallel_channel")
    coils = {s: _bar_range_ratio(s) for s in _SHAPE_LABELS if s != "parallel_channel"}
    assert control > 0.6, f"the control narrowed to {control:.2f} — it is coiling after all"
    worst = max(coils.values())
    assert worst < 0.8 * control, (
        f"the slackest coil narrows to {worst:.2f} against the control's {control:.2f} — the shapes "
        f"are no longer distinguishable from a channel by how their bars behave"
    )


@pytest.mark.parametrize("label", _SHAPE_LABELS)
def test_both_converging_lines_are_validated(label: str) -> None:
    """Three touches EACH: a coil drawn through two points on one side is a drawing (m31-l1)."""
    inj = get_injector("converging_lines")
    config = _config("converging_lines", [label])
    for seed in range(_SEEDS):
        result = inj.build(np.random.default_rng(seed), _N, label)
        f = _full(config, seed)
        hi = f.warmup + int(_SWING_F[-1] * _N) + 4
        for d in result.diagonals:
            # Each line's own anchor: the swings alternate, so the two do not start on the same bar.
            found = dg.touches(f.series, d, d.start, hi)
            assert len(found) >= 3, f"seed {seed}: {label} {d.label!r} has {len(found)} touches: {found}"


def test_the_resolution_family_reads_as_it_is_labelled() -> None:
    """Confirmed = a body through the line with volume; unconfirmed = through it on nobody's volume,
    and back inside. Holding = neither."""
    inj = get_injector("converging_lines")
    for label, through, volume_up in (
        ("break_confirmed", True, True),
        ("break_unconfirmed", False, False),
        ("compression_holding", False, None),
    ):
        config = _config("converging_lines", [label])
        for seed in range(150):
            result = inj.build(np.random.default_rng(seed), _N, label)
            f = _full(config, seed)
            lower = result.diagonals[1]
            a, b = f.warmup + int(0.92 * _N), f.warmup + _N - 8
            settled = float(np.median(np.asarray(f.series.close[a:b], dtype=float)))
            assert (settled < dg.price_at(lower, (a + b) // 2)) == through, (
                f"seed {seed}: {label} settled on the wrong side of the line it broke"
            )
            if volume_up is None:
                continue
            vol = result.volume_full
            assert vol is not None
            w = result.warmup
            ratio = float(
                np.median(vol[w + int(0.80 * _N) : w + int(0.88 * _N)])
                / np.median(vol[w + int(0.30 * _N) : w + int(0.70 * _N)])
            )
            assert (ratio > 1.6) == volume_up, f"seed {seed}: {label} volume ratio {ratio:.2f}"


# --- 6. the figures render the same lines, projected past the bars that drew them -----------------


def _panels(figure_id: str) -> list[Payload]:
    data = build_figure(load_figures(_CONTENT)[figure_id], "en")
    panels = data["panels"]
    assert isinstance(panels, list)
    return panels


def _figure_diagonal_panels() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for fid, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        out += [(fid, i) for i, panel in enumerate(_panels(fid)) if _drawn(panel)]
    return out


@pytest.mark.parametrize(("figure_id", "panel"), _figure_diagonal_panels())
def test_a_figure_projects_its_diagonals_to_its_own_right_edge(figure_id: str, panel: int) -> None:
    """The break is only visible against the line carried PAST the bars that drew it (m31-l1).

    A figure appends its resolution, so a diagonal that stopped where the injector's window did would
    leave the whole point of the figure drawn over empty space.
    """
    p = _panels(figure_id)[panel]
    s = p["series"]
    assert isinstance(s, dict)
    n = len(s["close"])
    for d in _drawn(p):
        assert int(str(d["end"])) == n - 1, (
            f"{figure_id} panel{panel}: {d['label']} stops at bar {d['end']} of {n} — the projection "
            f"the resolution is judged against is missing"
        )
        assert str(d["label"]), f"{figure_id} panel{panel}: diagonal with no label renders bare"


@pytest.mark.parametrize(("figure_id", "panel"), _figure_diagonal_panels())
def test_a_figure_diagonal_is_still_the_line_the_injector_drew(figure_id: str, panel: int) -> None:
    """Re-anchoring for the projection must not move the LINE: same slope, same price where it began."""
    p = _panels(figure_id)[panel]
    for d in _drawn(p):
        start, end = int(str(d["start"])), int(str(d["end"]))
        p0, p1 = float(str(d["start_price"])), float(str(d["end_price"]))
        s = p["series"]
        assert isinstance(s, dict)
        pre = len(s["close"]) - _RESOLUTION_CANDLES
        line = Diagonal(start=start, end=end, start_price=p0, end_price=p1, kind=str(d["kind"]))
        # The pre-resolution stretch is where the rhythm lives, so the line has to sit among those bars
        # rather than have been swung away by the extension. Counted on the CLOSES, with the same
        # `touches` the contract uses — NOT on the wicks. m31-l1 declares the anchoring criterion and
        # keeps it: this course anchors diagonals on bodies, so a support line sits just under the
        # closes and the wicks dip through it. Requiring a wick to straddle the line would be asserting
        # the criterion the lesson explicitly did not choose.
        series = Series(
            time=list(range(len(s["close"]))), open=s["open"], high=s["high"], low=s["low"],
            close=s["close"], volume=s["volume"],
        )
        visits = dg.touches(series, line, start, pre)
        assert len(visits) >= 3, (
            f"{figure_id} panel{panel}: {d['label']} is visited by {len(visits)} close(s) before the "
            f"resolution — the projection swung it off its own price action"
        )


def test_no_two_figures_draw_the_same_diagonal_anchor() -> None:
    """No two figures print the same anchor price — the next one picks a fresh tier or fails here.

    The `test_chart_levels.py` rule, applied to the primitive that arrived after it: every injector
    draws its base price from the same five-tier table with the same two opening draws, so two figures
    sharing a seed print identical prices to the cent and a reader meets the same chart twice.
    """
    where: dict[float, set[str]] = {}
    for figure_id, panel in _figure_diagonal_panels():
        for d in _drawn(_panels(figure_id)[panel]):
            for price in (float(str(d["start_price"])), float(str(d["end_price"]))):
                where.setdefault(round(price, 2), set()).add(figure_id)
    shared = {price: sorted(f) for price, f in where.items() if len(f) > 1}
    assert not shared, f"the same diagonal anchor drawn by different figures: {shared}"
