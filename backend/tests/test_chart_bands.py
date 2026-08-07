# SPDX-License-Identifier: AGPL-3.0-only
"""Shaded-zone integrity, for every injector that plants one and every figure that renders one.

A `Band` needs its own file rather than cases in `test_chart_levels.py` because it is withheld rather
than drawn (§1), and because its contract is asserted over hundreds of seeds rather than enforced by
moving wicks (§3, §4). §2 checks the *undrawn* `LevelGuard`s that the levels suite cannot discover;
§5 covers the two published figures.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns.base import PatternResult
from tradeschool.exercises.charts.patterns.imbalance import GAP_FLOOR, gap_spans
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.charts.types import Series
from tradeschool.exercises.figures import build_figure, load_figures
from tradeschool.exercises.pattern_chart import (
    PatternChartConfig,
    PatternChartGenerator,
    _full,
    _instantiate,
)

_SEEDS = 300  # per label — a zone's edges are candle extremes, so the defect is distributional
_N = 130
_KINDS = {"origin", "imbalance"}  # every kind the frontend has a colour and a title for
_CONTENT = Path(__file__).resolve().parents[2] / "content"
# Injectors that plant a zone. Named rather than only discovered, so an injector that silently STOPS
# publishing its band cannot make the discovered suites below vacuous by looking like it never had one.
_BAND_INJECTORS = {"origin_zone", "imbalance"}
_RESOLUTION_CANDLES = 24  # what a figure appends; mirrors `figures._RESOLUTION_CANDLES`

Payload = dict[str, object]


def _config(injector: str, targets: list[str], n: int = _N) -> PatternChartConfig:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": n, "targets": targets, "choices": list(get_injector(injector).labels)}
    )


def _bands(obj: Payload) -> list[dict[str, object]]:
    raw = obj.get("bands", [])
    assert isinstance(raw, list)
    return raw


def _edges(band: dict[str, object]) -> tuple[float, float]:
    return float(str(band["low"])), float(str(band["high"]))


def _visible(f: object) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(high, low, close) over the VISIBLE window of a `FullPatternChart` — warm-up trimmed."""
    full = f  # narrowed by use; `_full` returns a FullPatternChart
    s, w = full.series, full.warmup  # type: ignore[attr-defined]
    return (
        np.asarray(s.high[w:], dtype=float),
        np.asarray(s.low[w:], dtype=float),
        np.asarray(s.close[w:], dtype=float),
    )


def _marker(f: object, label: str) -> int:
    hits = [int(str(a["index"])) for a in f.annotations if a["label"] == label]  # type: ignore[attr-defined]
    assert len(hits) == 1, f"expected exactly one {label!r} marker, got {hits}"
    return hits[0]


def _injector_labels() -> list[tuple[str, str]]:
    return [(inj.name, label) for inj in all_injectors() for label in inj.labels]


def _band_labels() -> list[tuple[str, str]]:
    """(injector, label) pairs that plant a band, discovered so a new one is covered on registration."""
    out: list[tuple[str, str]] = []
    for inj in all_injectors():
        for label in inj.labels:
            if _full(_config(inj.name, [label]), 0).bands:
                out.append((inj.name, label))
    return out


_BAND_PAIRS = _band_labels()


# --- 1. a band is ground truth: never in the question, always in the answer -----------------------


@pytest.mark.parametrize(("injector", "label"), _injector_labels())
def test_no_exercise_payload_ever_carries_a_band(injector: str, label: str) -> None:
    """No pre-answer payload carries `bands` — asserted for EVERY injector, not just the two with zones."""
    config = _config(injector, [label])
    for seed in range(40):
        _lbl, _ann, payload = _instantiate(config, seed)
        assert "bands" not in payload, (
            f"seed {seed}: {injector}/{label} put a shaded zone in the pre-answer payload — that is the "
            f"answer to m30's own question"
        )


@pytest.mark.parametrize(("injector", "label"), _BAND_PAIRS)
def test_grading_reveals_the_band_it_withheld(injector: str, label: str) -> None:
    """...and grading hands the band over, on the same chart."""
    config = _config(injector, [label])
    gen = PatternChartGenerator()
    for seed in range(40):
        revealed = gen.grade(config, seed, {"label": label}, "en").correct_answer
        planted = _full(config, seed).bands
        assert revealed.get("bands") == planted, f"seed {seed}: {injector}/{label} band lost in grading"


def test_labels_that_plant_no_zone_publish_no_band() -> None:
    """`no_zone` and `no_imbalance` have no zone to reveal — a band would contradict the label."""
    for injector, label in (("origin_zone", "no_zone"), ("imbalance", "no_imbalance")):
        config = _config(injector, [label])
        for seed in range(60):
            assert not _full(config, seed).bands, f"seed {seed}: {injector}/{label} published a zone"


def test_every_injector_that_plants_a_band_is_covered() -> None:
    """Fails if the parametrised suites' discovery silently finds nothing."""
    assert {name for name, _label in _BAND_PAIRS} == _BAND_INJECTORS
    assert _figure_band_panels(), "no figure renders a zone — band rendering lost its figure coverage"


# --- 2. what every band owes, whatever it claims --------------------------------------------------


@pytest.mark.parametrize(("injector", "label"), _BAND_PAIRS)
def test_band_is_renderable_and_reads_as_a_zone(injector: str, label: str) -> None:
    """A band is placeable, titled, and wide enough to read as an area but not as a third of the chart.

    Both width bounds are load-bearing: earlier origin-zone windows collapsed to 0.17% and ran to 6.3%.
    """
    config = _config(injector, [label])
    for seed in range(_SEEDS):
        f = _full(config, seed)
        high, low, close = _visible(f)
        prices = set()
        for band in f.bands:
            lo, hi = _edges(band)
            assert lo < hi, f"seed {seed}: {injector}/{label} band low {lo} not below high {hi}"
            assert str(band["label"]), f"seed {seed}: {injector}/{label} band with no label renders bare"
            assert str(band["kind"]) in _KINDS, f"seed {seed}: unknown band kind {band['kind']!r}"
            width = (hi - lo) / float(close[0])
            assert 0.005 < width < 0.08, (
                f"seed {seed}: {injector}/{label} zone is {width:.2%} of price — "
                f"{'a hairline, not a zone' if width <= 0.005 else 'too wide to be wrong about anything'}"
            )
            # On screen, or the learner is shown nothing where the answer is.
            assert float(low.min()) <= lo and hi <= float(high.max()), (
                f"seed {seed}: {injector}/{label} zone [{lo}, {hi}] sits outside the rendered range"
            )
            assert (lo, hi) not in prices, f"seed {seed}: {injector}/{label} duplicate zone"
            prices.add((lo, hi))


@pytest.mark.parametrize(("injector", "label"), _BAND_PAIRS)
def test_undrawn_level_guards_are_honoured(injector: str, label: str) -> None:
    """A band's edge may ship a `LevelGuard` with no `Level` beside it — the contract without the line.

    The only place these are checked: the levels suite discovers its targets from PUBLISHED levels.
    """
    config = _config(injector, [label])
    inj = get_injector(injector)
    for seed in range(_SEEDS):
        result = inj.build(np.random.default_rng(seed), _N, label)
        f = _full(config, seed)
        high, low, close = _visible(f)
        w = f.warmup
        for g in result.level_guards:
            edge = high if g.kind == "resistance" else low
            for lo, hi in g.no_breach:
                a, b = max(0, lo - w), min(hi - w, len(high))
                if a >= b:
                    continue
                beyond = (edge[a:b] > g.price) if g.kind == "resistance" else (edge[a:b] < g.price)
                bodies = (close[a:b] > g.price) if g.kind == "resistance" else (close[a:b] < g.price)
                assert not beyond.any(), (
                    f"seed {seed}: {injector}/{label} wick beyond undrawn {g.kind} {g.price} in [{a},{b})"
                )
                assert not bodies.any(), (
                    f"seed {seed}: {injector}/{label} CLOSE beyond undrawn {g.kind} {g.price}"
                )


# --- 3. the `origin` contract: the zone precedes the break, and the return reached it -------------

_ORIGIN_LABELS = ("zone_respected", "zone_failed")


@pytest.mark.parametrize("label", _ORIGIN_LABELS)
def test_origin_zone_precedes_the_break_it_is_the_origin_of(label: str) -> None:
    """The claim in order: zone candles, then the impulse closing past the tested high, then the return."""
    config = _config("origin_zone", [label])
    for seed in range(_SEEDS):
        f = _full(config, seed)
        high, _low, close = _visible(f)
        origin, bos, retest = _marker(f, "origin"), _marker(f, "BOS"), _marker(f, "retest")
        assert origin < bos < retest, (
            f"seed {seed}: {label} sequence out of order (origin {origin}, BOS {bos}, retest {retest})"
        )
        prior = float(high[:origin].max())
        assert float(close[bos]) > prior, (
            f"seed {seed}: {label} the BOS bar closes at {close[bos]:.2f}, not past the prior "
            f"high {prior:.2f}"
        )
        # ...and past it by a margin nobody has to squint at, on the CLOSE.
        #
        # The distinction is the whole of m08-l1's rule and it is easy to assert weakly. `close[bos] > prior`
        # above is true by construction and carries no margin at all: `bos` is by definition the FIRST bar
        # to close past the high, and measured over 600 label x seed samples that first close clears it by as
        # little as +0.0013% — a tie. A margin on the HIGH would be worse than nothing here, because a wick
        # through a level is precisely the ambiguous case m08-l1 says to wait through, so "clean past" would
        # be certified by the one piece of evidence the course tells you not to trade.
        #
        # So the margin is asserted where the claim lives: the impulse's BODY has to settle clear of the
        # high. Measured floor across the same 600 samples is +3.40%, so 2% is a real bound with headroom
        # rather than a threshold traced around the current output.
        best_close = float(close[bos : retest + 1].max())
        assert best_close > prior * 1.02, (
            f"seed {seed}: {label} the impulse's best CLOSE is {best_close:.2f}, only "
            f"{best_close / prior - 1:+.2%} past the prior high {prior:.2f} — not a clean break"
        )


@pytest.mark.parametrize("label", _ORIGIN_LABELS)
def test_the_return_actually_trades_into_the_origin_zone(label: str) -> None:
    """The marked return bar's range overlaps the zone — the claim both labels are built on."""
    config = _config("origin_zone", [label])
    for seed in range(_SEEDS):
        f = _full(config, seed)
        high, low, _close = _visible(f)
        lo, hi = _edges(f.bands[0])
        r = _marker(f, "retest")
        assert low[r] < hi and high[r] > lo, (
            f"seed {seed}: {label} the return bar [{low[r]:.2f}, {high[r]:.2f}] never reaches the zone "
            f"[{lo:.2f}, {hi:.2f}]"
        )


def test_respected_and_failed_differ_by_side_and_not_by_distance() -> None:
    """Which SIDE of the zone price ends on is the answer; how FAR must not be readable off a ruler."""
    dist: dict[str, list[float]] = {}
    for label in _ORIGIN_LABELS:
        config = _config("origin_zone", [label])
        for seed in range(200):
            f = _full(config, seed)
            _high, _low, close = _visible(f)
            lo, hi = _edges(f.bands[0])
            mid = (lo + hi) / 2
            dist.setdefault(label, []).append(abs(float(close[-1]) - mid) / mid)
    means = {k: float(np.mean(v)) for k, v in dist.items()}
    spread = max(means.values()) - min(means.values())
    assert spread < 0.02, f"distance from the zone leaks the label: {means}"


def test_a_respected_zone_holds_and_a_failed_one_does_not() -> None:
    """A respected zone is never closed through and ends above; a failed one is, and ends below."""
    for label in _ORIGIN_LABELS:
        config = _config("origin_zone", [label])
        for seed in range(_SEEDS):
            f = _full(config, seed)
            _high, _low, close = _visible(f)
            lo, hi = _edges(f.bands[0])
            after = close[_marker(f, "retest") :]
            if label == "zone_respected":
                assert float(after.min()) >= lo, (
                    f"seed {seed}: a respected zone was closed through ({after.min():.2f} < {lo:.2f})"
                )
                assert float(close[-1]) > hi, f"seed {seed}: a respected zone should end above the zone"
            else:
                assert float(after.min()) < lo, f"seed {seed}: a failed zone was never closed through"
                assert float(close[-1]) < lo, f"seed {seed}: a failed zone should end below the zone"


def test_no_zone_never_breaks_structure() -> None:
    """The `no_zone` rally never takes out the prior high, wick included — that absence IS the answer."""
    config = _config("origin_zone", ["no_zone"])
    for seed in range(_SEEDS):
        f = _full(config, seed)
        high, _low, _close = _visible(f)
        n = len(high)
        prior = float(high[: int(0.44 * n)].max())
        assert float(high.max()) <= prior, (
            f"seed {seed}: no_zone printed a high of {high.max():.2f} above the prior high {prior:.2f} — "
            f"that chart does contain a break"
        )
        assert _marker(f, "failed_break") > int(0.44 * n), "the failed rally is marked after the range"


# --- 3b. the generated set is bull-only, and the prompts depend on it -----------------------------
#
# Both injectors plant only the bullish case. The mechanic is symmetric and the lesson says so, but the
# generated set is not, because m30-ex-1 and m30-ex-2 describe the bullish geometry IN WORDS — "a close
# clean past the high the range had been testing", "one candle's HIGH below the LOW of the candle two bars
# later". A bearish seed served under those prompts would be graded against a question describing the
# mirror of what is on screen: the learner reads the prompt, looks for a broken high, and the chart has a
# broken low. That is not a leak, it is worse — an unanswerable question with a confident ground truth.
#
# So these two tests exist to FAIL when a bearish variant is added, and to fail loudly enough to say what
# has to change with it: both prompts and the lesson passage, in ES and EN, before the injector ships it.


@pytest.mark.parametrize("label", ["zone_respected", "zone_failed", "no_zone"])
def test_origin_zone_only_ever_plants_the_bullish_case(label: str) -> None:
    for seed in range(_SEEDS):
        f = _full(_config("origin_zone", [label]), seed)
        _high, _low, close = _visible(f)
        n = len(close)
        kinds = {str(a["label"]): str(a["kind"]) for a in f.annotations}
        # The break is of a HIGH and the zone is demand: the markers carry that, so they are the check.
        for marker, want in (("origin", "low"), ("BOS", "high"), ("retest", "low"), ("failed_break", "high")):
            if marker in kinds:
                assert kinds[marker] == want, (
                    f"seed {seed}: {label} marker {marker!r} is {kinds[marker]!r}, not {want!r} — a bearish "
                    f"variant has appeared. m30-l1 and m30-ex-1 describe the bullish case in words (ES+EN); "
                    f"make them symmetric before shipping it."
                )
        assert float(close[int(0.66 * n)]) > float(close[int(0.47 * n)]), (
            f"seed {seed}: {label} the move out of the zone is DOWN — see the message above"
        )


@pytest.mark.parametrize("label", ["imbalance_unfilled", "imbalance_filled", "no_imbalance"])
def test_imbalance_only_ever_plants_the_bullish_case(label: str) -> None:
    for seed in range(_SEEDS):
        f = _full(_config("imbalance", [label]), seed)
        s = _series_of(f)
        for i, _lo, _hi in gap_spans(s, f.warmup, len(s.close)):
            # `gap_spans` reports both directions; only the up-gap branch may ever fire here.
            assert s.low[i + 2] > s.high[i], (
                f"seed {seed}: {label} planted a BEARISH imbalance at bar {i} — m30-l1 and m30-ex-2 describe "
                f"the up-gap in words (ES+EN); make them symmetric before shipping it."
            )
        if label != "no_imbalance":
            g = f.warmup + _marker(f, "imbalance")
            assert s.close[g] > s.close[g - 1], (
                f"seed {seed}: {label} the impulse candle is bearish — see the message above"
            )


# --- 4. the `imbalance` contract: crossed in one candle, and unique on the chart ------------------


def _series_of(f: object) -> Series:
    return f.series  # type: ignore[attr-defined,no-any-return]


@pytest.mark.parametrize("label", ["imbalance_unfilled", "imbalance_filled"])
def test_the_band_is_the_span_crossed_inside_one_candle(label: str) -> None:
    """The definition, measured on the RENDERED candles: predecessor's high below successor's low.

    Cannot be enforced — at the impulse bar `build_series` draws wicks large enough to swallow the gap.
    """
    config = _config("imbalance", [label])
    for seed in range(_SEEDS):
        f = _full(config, seed)
        s = _series_of(f)
        g = f.warmup + _marker(f, "imbalance")
        lo, hi = _edges(f.bands[0])
        assert s.high[g - 1] == lo, f"seed {seed}: {label} zone floor is not the prior candle's high"
        assert s.low[g + 1] == hi, f"seed {seed}: {label} zone ceiling is not the next candle's low"
        assert hi - lo > GAP_FLOOR * s.close[g], f"seed {seed}: {label} span below the readable floor"
        # Exactly one candle covers it: the impulse. Any other bar with range inside the span would mean
        # the span was traded through more than once, and "almost nothing traded here" would be false.
        crossers = [
            j
            for j in range(f.warmup, len(s.close))
            if s.low[j] < hi and s.high[j] > lo
        ]
        assert crossers[0] == g, f"seed {seed}: {label} something crossed the span before the impulse"


def test_every_chart_carries_at_most_one_imbalance() -> None:
    """One gap per chart, so the question has a single subject; `no_imbalance` has none at all."""
    for label in get_injector("imbalance").labels:
        config = _config("imbalance", [label])
        expected = 0 if label == "no_imbalance" else 1
        for seed in range(_SEEDS):
            f = _full(config, seed)
            s = _series_of(f)
            spans = gap_spans(s, f.warmup, len(s.close))
            assert len(spans) == expected, (
                f"seed {seed}: {label} chart carries {len(spans)} imbalances, expected {expected}"
                + (f" — spans {[(round(a, 2), round(b, 2)) for _i, a, b in spans][:3]}" if spans else "")
            )
            if expected:
                lo, hi = _edges(f.bands[0])
                assert (spans[0][1], spans[0][2]) == (lo, hi), (
                    f"seed {seed}: {label} the detected span is not the published zone"
                )


def test_unfilled_stays_open_and_filled_is_traded_clean_through() -> None:
    """An open gap has no later candle ranging into it; a filled one is traded clean past its far edge."""
    for label, filled in (("imbalance_unfilled", False), ("imbalance_filled", True)):
        config = _config("imbalance", [label])
        for seed in range(_SEEDS):
            f = _full(config, seed)
            s = _series_of(f)
            g = f.warmup + _marker(f, "imbalance")
            lo, hi = _edges(f.bands[0])
            later = range(g + 2, len(s.close))
            entered = [j for j in later if s.low[j] < hi and s.high[j] > lo]
            through = [j for j in later if s.low[j] < lo]
            if filled:
                assert through, f"seed {seed}: {label} was never traded clean through"
                assert f.warmup + _marker(f, "revisit") in entered, (
                    f"seed {seed}: the revisit marker is not on a bar inside the zone"
                )
            else:
                assert not entered, (
                    f"seed {seed}: {label} was traded back into at bars {entered[:3]} — the gap is not open"
                )


# --- 5. the two published figures render their zone against the action they claim -----------------


def _panels(figure_id: str) -> list[Payload]:
    data = build_figure(load_figures(_CONTENT)[figure_id], "en")
    panels = data["panels"]
    assert isinstance(panels, list)
    return panels


def _figure_band_panels() -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for fid, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        out += [(fid, i) for i, panel in enumerate(_panels(fid)) if _bands(panel)]
    return out


def _hlc(panel: Payload) -> tuple[list[float], list[float], list[float]]:
    s = panel["series"]
    assert isinstance(s, dict)
    return s["high"], s["low"], s["close"]


@pytest.mark.parametrize(("figure_id", "panel"), _figure_band_panels())
def test_figure_zone_is_reached_by_the_action_it_is_drawn_over(figure_id: str, panel: int) -> None:
    """Every figure zone is somewhere the chart visibly went, and carries a title."""
    p = _panels(figure_id)[panel]
    high, low, _close = _hlc(p)
    for band in _bands(p):
        lo, hi = _edges(band)
        assert str(band["label"]), f"{figure_id} panel{panel}: zone with no label renders bare"
        assert any(low[j] < hi and high[j] > lo for j in range(len(high))), (
            f"{figure_id} panel{panel}: zone [{lo}, {hi}] is never reached by any candle"
        )


def test_no_two_figures_draw_the_same_zone_edge() -> None:
    """No two figures print the same zone edge — or the same edge as a LEVEL price.

    Every injector draws its base price from the same five-tier table, so one seed gives an identical
    anchor.
    """
    where: dict[float, set[str]] = {}
    for figure_id, panel in _figure_band_panels():
        for band in _bands(_panels(figure_id)[panel]):
            for edge in _edges(band):
                where.setdefault(edge, set()).add(figure_id)
    for figure_id, spec in sorted(load_figures(_CONTENT).items()):
        if spec.kind != "chart":
            continue
        for p in _panels(figure_id):
            levels = p["levels"]
            assert isinstance(levels, list)
            for lvl in levels:
                where.setdefault(float(str(lvl["price"])), set()).add(figure_id)
    shared = {price: sorted(f) for price, f in where.items() if len(f) > 1}
    assert not shared, f"the same price drawn by different figures: {shared}"


def test_the_origin_zone_figure_shows_the_move_running_away_from_the_zone() -> None:
    """m30-l1's prose claim: the zone held and the continuation is on screen. Frozen seed."""
    p = _panels("fig-m30-origin-zone")[0]
    _high, low, close = _hlc(p)
    lo, _hi = _edges(_bands(p)[0])
    pre = len(close) - _RESOLUTION_CANDLES
    assert min(low[pre:]) > lo, "the resolution traded back through the zone it is supposed to have held"
    assert close[-1] > max(close[:pre]), "the resolution should carry price beyond the pre-resolution high"


def test_the_imbalance_figure_shows_the_revisit_an_exercise_cuts_off() -> None:
    """The zone is untouched before the resolution and reached inside it — the figure/exercise split."""
    p = _panels("fig-m30-imbalance")[0]
    high, low, close = _hlc(p)
    lo, hi = _edges(_bands(p)[0])
    pre = len(close) - _RESOLUTION_CANDLES
    annotations = p["annotations"]
    assert isinstance(annotations, list)
    gap_bar = next(int(str(a["index"])) for a in annotations if a["label"] == "imbalance")
    assert not [j for j in range(gap_bar + 2, pre) if low[j] < hi and high[j] > lo], (
        "the gap is traded back into before the resolution — the exercise window would not be 'unfilled'"
    )
    # The revisit is CONTAINED in the span: it reaches inside it and stops there. Both halves matter and
    # they fail in opposite directions — too shallow and the figure shows no revisit at all under a caption
    # that promises one; too deep and it shows price trading clean through, which is the
    # `imbalance_filled` picture under a caption saying the gap stayed open. The leg is tuned (a
    # `strength` in the figure spec), and this is what makes the tuning a tested property rather than a
    # number somebody once eyeballed: retune it either way and this fails.
    deepest = min(low[pre:])
    assert lo <= deepest <= hi, (
        f"the revisit's low is {deepest:.2f}, outside the span [{lo:.2f}, {hi:.2f}] — "
        f"{'it never reached the gap' if deepest > hi else 'it traded clean through the gap'}"
    )


# --- the batch's one shared-path edit ------------------------------------------------------------


def test_grading_is_identical_whether_read_from_full_or_instantiate() -> None:
    """`grade()` reading `_full` instead of `_instantiate` is a no-op, over every injector and locale.

    Needs its own test: the golden suite fingerprints `_instantiate`'s payload, so it cannot see this.
    """
    gen = PatternChartGenerator()
    checked = 0
    for inj in all_injectors():
        labels = list(inj.labels)
        config = _config(inj.name, labels)
        for seed in range(8):
            for locale in ("en", "es"):
                label, annotations, _payload = _instantiate(config, seed)
                result = gen.grade(config, seed, {"label": labels[0]}, locale)
                # The pre-change reveal, verbatim: {"label", "annotations"} off `_instantiate`.
                assert result.correct_answer["label"] == label, f"{inj.name}/{seed}: label changed"
                assert result.correct_answer["annotations"] == annotations, (
                    f"{inj.name}/{seed}: annotations changed"
                )
                assert result.correct == (labels[0] == label), f"{inj.name}/{seed}: verdict changed"
                # ...and the ONLY key the reveal gained is `bands`, on the injectors that plant one.
                extra = set(result.correct_answer) - {"label", "annotations"}
                assert extra <= {"bands"}, f"{inj.name}: grading revealed unexpected keys {extra}"
                assert bool(extra) == (inj.name in _BAND_INJECTORS and bool(_full(config, seed).bands))
                checked += 1
    assert checked == len(all_injectors()) * 8 * 2


def test_band_is_part_of_the_injector_contract() -> None:
    """`bands` lives on `PatternResult` next to `levels`, not as an optional extra."""
    result = get_injector("origin_zone").build(np.random.default_rng(0), _N, "zone_respected")
    assert isinstance(result, PatternResult)
    assert result.bands and result.bands[0].kind in _KINDS
    assert PatternResult(close_full=result.close_full, warmup=0, label="x").bands == []
