# SPDX-License-Identifier: AGPL-3.0-only
"""Phase-2 generic pattern-chart generator + its injectors.

The blocking gate for EVERY injector (round-6 rule, now permanent):
  * credibility — the last candles are drift-free ambient noise, so no synthetic-looking spike ends
    the chart (checked for every injector);
  * anti-leak  — for detection injectors (``hides_resolution``) the distribution of the final candles
    must NOT be predictive of the label (no label pair separable on last-3 net/abs return).
"""

from __future__ import annotations

import numpy as np
import pytest

from tradeschool.exercises.charts.patterns.common import TAIL
from tradeschool.exercises.charts.patterns.registry import all_injectors, get_injector
from tradeschool.exercises.pattern_chart import PatternChartGenerator, _instantiate

_THRESH = 4.0  # Welch |t| ceiling — above this the groups are statistically separable (a leak)
_PER = 90  # charts per label for the statistical tests


def _config(injector: str, targets: list[str], choices: list[str]) -> object:
    gen = PatternChartGenerator()
    return gen.parse_config(
        {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": injector,
         "n": 130, "targets": targets, "choices": choices}
    )


def _welch_t(a: np.ndarray, b: np.ndarray) -> float:
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else 0.0


def _last3(close: np.ndarray) -> tuple[float, float]:
    r = np.diff(np.log(close))[-3:]
    return float(r.sum()), float(np.mean(np.abs(r)))


def _collect(injector_name: str, label: str, per: int) -> tuple[np.ndarray, np.ndarray, float]:
    """(net last-3 returns, abs last-3 returns, max |single-candle return| in the last 6) over seeds."""
    labels = list(get_injector(injector_name).labels)
    config = _config(injector_name, [label], labels)
    nets, abss, tail_max = [], [], 0.0
    for seed in range(per):
        _label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        close = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        net, ab = _last3(close)
        nets.append(net)
        abss.append(ab)
        tail_max = max(tail_max, float(np.max(np.abs(np.diff(np.log(close))[-6:]))))
    return np.array(nets), np.array(abss), tail_max


@pytest.mark.parametrize("injector", [inj.name for inj in all_injectors()])
def test_injector_last_candles_are_credible(injector: str) -> None:
    """No injector may end on a synthetic spike: every candle in the ambient tail stays within a few
    fixed sigmas of a normal continuation move (TAIL_SIGMA≈0.9%)."""
    for label in get_injector(injector).labels:
        _net, _abs, tail_max = _collect(injector, label, 40)
        assert tail_max < 0.05, f"{injector}/{label}: tail candle {tail_max:.3f} looks synthetic"


@pytest.mark.parametrize("injector", [inj.name for inj in all_injectors() if inj.hides_resolution])
def test_detection_injector_last_candles_do_not_leak_label(injector: str) -> None:
    """For detection injectors the final candles must not separate any pair of labels (round-6 rule):
    the resolution is off screen and the tail is the same ambient distribution for every label."""
    labels = list(get_injector(injector).labels)
    nets = {lbl: _collect(injector, lbl, _PER)[0] for lbl in labels}
    abss = {lbl: _collect(injector, lbl, _PER)[1] for lbl in labels}

    for i, a in enumerate(labels):
        # No systematic drift in any label's final candles.
        se = nets[a].std(ddof=1) / np.sqrt(len(nets[a]))
        assert abs(nets[a].mean()) < _THRESH * se, f"{injector}/{a}: final candles drift"
        for b in labels[i + 1 :]:
            assert abs(_welch_t(nets[a], nets[b])) < _THRESH, f"{injector}: {a} vs {b} net leaks"
            assert abs(_welch_t(abss[a], abss[b])) < _THRESH, f"{injector}: {a} vs {b} size leaks"


# --- fakeout (m08) correctness: the visible structure actually encodes the label -----------------


def _fakeout_beyond(close: float, level: float, kind: str) -> bool:
    return close > level if kind == "resistance" else close < level


def test_fakeout_structure_matches_label() -> None:
    """The visible geometry encodes the label robustly: where price SETTLED (median of the hold
    plateau, ignoring the noisy ambient tail) relative to the level, and — for a false break — the
    fact that it did poke beyond during the decision before failing."""
    config = _config("fakeout", ["genuine_breakout", "false_break", "no_break"],
                     ["genuine_breakout", "false_break", "no_break"])
    seen = {"genuine_breakout": 0, "false_break": 0, "no_break": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        levels = payload["levels"]  # type: ignore[index]
        assert levels, "fakeout must expose the tested level"
        level = float(levels[0]["price"])
        kind = str(levels[0]["kind"])
        closes = [float(c) for c in payload["series"]["close"]]  # type: ignore[index]
        n = len(closes)
        core = closes[: n - TAIL]  # the designed structure; the ambient tail is deliberately noisy
        settled = float(np.median(closes[int(0.88 * n) : n - TAIL]))  # hold plateau (pre-tail)
        settled_beyond = _fakeout_beyond(settled, level, kind)
        ever_beyond = any(_fakeout_beyond(c, level, kind) for c in core)
        if label == "genuine_breakout":
            assert settled_beyond, f"seed {seed}: genuine breakout should settle beyond the level"
        elif label == "false_break":
            assert ever_beyond and not settled_beyond, f"seed {seed}: false break should poke then fail"
        else:  # no_break
            assert not ever_beyond, f"seed {seed}: no_break should never trade beyond the level"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- ma_context (m10) correctness: MA order + net drift match the labelled regime ----------------


def test_ma_context_structure_matches_label() -> None:
    config = _config("ma_context", ["uptrend", "downtrend", "range"], ["uptrend", "downtrend", "range"])
    seen = {"uptrend": 0, "downtrend": 0, "range": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        closes = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        overlays = payload["overlays"]  # type: ignore[index]
        fast = np.asarray(overlays["ema20"], dtype=float)
        slow = np.asarray(overlays["ema50"], dtype=float)
        n = len(closes)
        k = n - TAIL - 1  # last structural candle (before the ambient tail)
        third = n // 3
        # Net drift as the ratio of the last third's mean to the first third's mean — averages out
        # the oscillation so a genuine range reads flat while a trend reads clearly directional.
        drift = float(np.mean(closes[k - third : k]) / np.mean(closes[:third]) - 1.0)
        if label == "uptrend":
            assert drift > 0.08, f"seed {seed}: uptrend drift {drift:.2f} too weak"
            assert fast[k] > slow[k], f"seed {seed}: uptrend fast MA should lead the slow MA"
        elif label == "downtrend":
            assert drift < -0.08, f"seed {seed}: downtrend drift {drift:.2f} too weak"
            assert fast[k] < slow[k], f"seed {seed}: downtrend fast MA should trail the slow MA"
        else:  # range
            assert abs(drift) < 0.05, f"seed {seed}: range drift {drift:.2f} too large"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- oscillator_reading (m11) correctness: the rendered RSI reads as labelled -------------------


def test_oscillator_reading_matches_label() -> None:
    config = _config("oscillator_reading", ["overbought", "oversold", "neutral"],
                     ["overbought", "oversold", "neutral"])
    seen = {"overbought": 0, "oversold": 0, "neutral": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        rsi_series = np.asarray(payload["rsi"], dtype=float)  # type: ignore[index]
        # Never peg at the extremes — a real RSI(14) does not sit at 0/100 (round-3 rule).
        assert rsi_series.max() < 97 and rsi_series.min() > 3, f"seed {seed}: RSI pegged"
        # Read the RSI over the last structural stretch (before the gentle end), as a learner would.
        reading = float(np.median(rsi_series[-12:]))
        if label == "overbought":
            assert reading > 68, f"seed {seed}: overbought RSI only {reading:.0f}"
        elif label == "oversold":
            assert reading < 32, f"seed {seed}: oversold RSI only {reading:.0f}"
        else:
            assert 35 < reading < 65, f"seed {seed}: neutral RSI {reading:.0f} not mid-range"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- macd_cross (m11) correctness: the rendered MACD shows the labelled crossover picture --------


def _side_changes(values: np.ndarray) -> list[int]:
    """Indices where a series changes side. An exact 0.0 (a payload value rounded to 4dp) is treated
    as still belonging to the previous side, so one zero can never count as two crossings."""
    idx: list[int] = []
    prev = 0.0
    for i, v in enumerate(values):
        side = float(np.sign(v))
        if side == 0.0:
            continue
        if prev != 0.0 and side != prev:
            idx.append(i)
        prev = side
    return idx


def test_macd_cross_matches_label() -> None:
    """The three labels are separated by the single quantity the learner reads off the pane: how often
    the MACD LINE crosses zero. Never — the only cross is against the signal line, a wobble inside an
    intact trend. Once, late — the fast EMA crossed the slow one: a regime change. Repeatedly — a
    range where every cross whipsaws."""
    labels = ["signal_cross", "zero_cross", "whipsaw"]
    config = _config("macd_cross", labels, labels)
    seen = dict.fromkeys(labels, 0)
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        macd_payload = payload["macd"]  # type: ignore[index]
        line = np.asarray(macd_payload["line"], dtype=float)
        hist = np.asarray(macd_payload["hist"], dtype=float)
        closes = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        n = len(line)
        crossings = _side_changes(line)
        third = n // 3
        # Net drift as a ratio of thirds (as in ma_context): averages the oscillation out, so a range
        # reads flat while a trend reads clearly directional.
        drift = float(np.mean(closes[-third:]) / np.mean(closes[:third]) - 1.0)
        if label == "signal_cross":
            assert not crossings, f"seed {seed}: the MACD line must stay one side of zero, {crossings}"
            assert any(i > 0.65 * n for i in _side_changes(hist)), f"seed {seed}: no recent signal cross"
            assert abs(drift) > 0.08, f"seed {seed}: needs an intact trend, drift only {drift:.2f}"
            # The cross must still be readable at the right edge, not faded back out by the last bars.
            assert np.sign(hist[-1]) == np.sign(drift), f"seed {seed}: histogram ends against the trend"
        elif label == "zero_cross":
            assert len(crossings) == 1, f"seed {seed}: expected exactly one zero cross, got {crossings}"
            assert crossings[0] > 0.6 * n, f"seed {seed}: zero cross too early ({crossings[0]}/{n})"
            assert np.sign(line[-1]) != np.sign(line[0]), f"seed {seed}: MACD ends the side it began"
        else:  # whipsaw
            assert len(crossings) >= 4, f"seed {seed}: whipsaw needs repeated zero crosses, {crossings}"
            assert abs(drift) < 0.05, f"seed {seed}: whipsaw must be a range, drift {drift:.2f}"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- fibonacci (m13) correctness: the pullback extreme sits at the labelled fib level ------------


def test_fibonacci_pullback_hits_labelled_level() -> None:
    config = _config("fibonacci", ["retrace_382", "retrace_500", "retrace_618"],
                     ["retrace_382", "retrace_500", "retrace_618"])
    seen = {"retrace_382": 0, "retrace_500": 0, "retrace_618": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        closes = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        levels = {lv["label"]: float(lv["price"]) for lv in payload["levels"]}  # type: ignore[index]
        n = len(closes)
        up = closes[int(0.5 * n)] > closes[0]  # up impulse -> pullback is a low; else a high
        window = closes[int(0.60 * n) : int(0.88 * n)]  # the pullback region
        extreme = float(np.min(window)) if up else float(np.max(window))
        nearest = min(levels.items(), key=lambda kv: abs(extreme - kv[1]))
        assert nearest[0] == label.split("_")[1], (
            f"seed {seed}: pullback extreme nearest {nearest[0]}, labelled {label}"
        )
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- volume_confirmation (m14) correctness: the break-candle volume carries the label ------------


def test_volume_confirmation_matches_label() -> None:
    config = _config("volume_confirmation", ["confirmed_breakout", "unconfirmed_breakout"],
                     ["confirmed_breakout", "unconfirmed_breakout"])
    seen = {"confirmed_breakout": 0, "unconfirmed_breakout": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        vol = np.asarray(payload["series"]["volume"], dtype=float)  # type: ignore[index]
        n = len(vol)
        range_med = float(np.median(vol[: int(0.70 * n)]))  # typical volume before the break
        break_vol = float(np.max(vol[int(0.77 * n) : int(0.87 * n)]))  # volume at the break
        ratio = break_vol / range_med
        if label == "confirmed_breakout":
            assert ratio > 2.2, f"seed {seed}: confirmed break volume ratio only {ratio:.1f}"
        else:
            assert ratio < 1.6, f"seed {seed}: unconfirmed break volume ratio {ratio:.1f} too high"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- wyckoff (m09) correctness: prior trend + spring/upthrust match the schematic ----------------


def test_wyckoff_structure_matches_label() -> None:
    config = _config("wyckoff", ["accumulation", "distribution", "none"],
                     ["accumulation", "distribution", "none"])
    seen = {"accumulation": 0, "distribution": 0, "none": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        closes = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        lv = {x["label"]: float(x["price"]) for x in payload["levels"]}  # type: ignore[index]
        support, resistance = lv["support"], lv["resistance"]
        n = len(closes)
        event = closes[int(0.68 * n) : int(0.82 * n)]  # spring / upthrust window
        prior_early = float(np.mean(closes[: int(0.12 * n)]))
        range_mid = float(np.mean(closes[int(0.40 * n) : int(0.62 * n)]))
        broke_below = float(np.min(event)) < support * 0.995
        broke_above = float(np.max(event)) > resistance * 1.005
        never_out = closes.min() > support * 0.995 and closes.max() < resistance * 1.005
        if label == "accumulation":
            assert broke_below and not broke_above, f"seed {seed}: no clean spring below support"
            assert prior_early > range_mid, f"seed {seed}: accumulation needs a prior downtrend"
        elif label == "distribution":
            assert broke_above and not broke_below, f"seed {seed}: no clean upthrust above resistance"
            assert prior_early < range_mid, f"seed {seed}: distribution needs a prior uptrend"
        else:  # none — stays inside the range, no false break
            assert never_out, f"seed {seed}: 'none' should not break the range"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- derivatives (m17) correctness: OI trend matches the label; price is identical across labels --


def test_derivatives_oi_matches_label() -> None:
    config = _config("derivatives", ["rising_oi", "falling_oi", "flat_oi"],
                     ["rising_oi", "falling_oi", "flat_oi"])
    seen = {"rising_oi": 0, "falling_oi": 0, "flat_oi": 0}
    for seed in range(60):
        label, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        oi = np.asarray(payload["oi"], dtype=float)  # type: ignore[index]
        net = float(np.mean(oi[-15:]) / np.mean(oi[:15]) - 1.0)
        if label == "rising_oi":
            assert net > 0.12, f"seed {seed}: rising_oi net {net:.2f} too weak"
        elif label == "falling_oi":
            assert net < -0.12, f"seed {seed}: falling_oi net {net:.2f} too weak"
        else:
            assert abs(net) < 0.08, f"seed {seed}: flat_oi net {net:.2f} too large"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


def test_derivatives_price_is_label_independent() -> None:
    """Price must be built identically for every label (only OI carries the signal), so the same
    seed yields the same candles regardless of which OI label was requested."""
    gen = PatternChartGenerator()
    seeds_price: dict[str, list[float]] = {}
    for label in ("rising_oi", "falling_oi", "flat_oi"):
        cfg = gen.parse_config(
            {"type": "pattern_chart", "prompt": {"en": "x", "es": "x"}, "injector": "derivatives",
             "n": 130, "targets": [label], "choices": ["rising_oi", "falling_oi", "flat_oi"]}
        )
        _lbl, _ann, payload = _instantiate(cfg, 3)  # type: ignore[arg-type]
        seeds_price[label] = payload["series"]["close"]  # type: ignore[index]
    assert seeds_price["rising_oi"] == seeds_price["falling_oi"] == seeds_price["flat_oi"]


# --- cvd_divergence (m26) correctness: the CVD pane reads as labelled at the two swings ----------

_CVD_LABELS = ("cvd_bullish_divergence", "cvd_bearish_divergence", "cvd_confirms")
_PRICE_EPS = 0.002  # a new extreme must clear this fraction of price to count as read-able
_CVD_EPS = 0.05  # ...and the CVD step this fraction of the visible CVD range


def _swing_pair(annotations: list[dict]) -> tuple[int, int, str]:
    """The two ground-truth swing indices (visible coords) and their kind, as grading reveals them."""
    swings = sorted((a for a in annotations if a["label"] in ("1", "2")), key=lambda a: a["label"])
    assert len(swings) == 2, f"expected two swing annotations, got {annotations}"
    return int(swings[0]["index"]), int(swings[1]["index"]), str(swings[0]["kind"])


def test_cvd_divergence_matches_label() -> None:
    """The rendered pane must encode the label at the two swings the solution points at: price makes a
    new extreme, and CVD either refuses to follow it (a divergence) or makes its own new extreme with
    it (confirmation). This is the read the lesson teaches, checked on the payload the learner sees."""
    config = _config("cvd_divergence", list(_CVD_LABELS), list(_CVD_LABELS))
    seen = dict.fromkeys(_CVD_LABELS, 0)
    for seed in range(60):
        label, ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
        seen[label] += 1
        s1, s2, kind = _swing_pair(ann)
        close = np.asarray(payload["series"]["close"], dtype=float)  # type: ignore[index]
        cvd = np.asarray(payload["cvd"], dtype=float)  # type: ignore[index]
        assert len(cvd) == len(close), f"seed {seed}: CVD must align 1:1 with the candles"
        sign = -1.0 if kind == "low" else 1.0  # the direction price is making its new extreme in
        price_step = sign * float(close[s2] - close[s1])
        cvd_step = sign * float(cvd[s2] - cvd[s1])
        span = float(np.max(cvd) - np.min(cvd))
        assert price_step > _PRICE_EPS * float(close[s1]), (
            f"seed {seed}/{label}: no clear new price extreme at swing 2 ({price_step:.2f})"
        )
        if label == "cvd_confirms":
            assert cvd_step > _CVD_EPS * span, (
                f"seed {seed}: cvd_confirms needs CVD making its new extreme WITH price"
            )
        else:
            assert cvd_step < -_CVD_EPS * span, (
                f"seed {seed}/{label}: CVD must refuse price's new extreme (step {cvd_step:.0f})"
            )
        # ...and the divergence label must be the one matching the side price is extending to.
        if label == "cvd_bullish_divergence":
            assert kind == "low", f"seed {seed}: bullish absorption must sit at a low"
        elif label == "cvd_bearish_divergence":
            assert kind == "high", f"seed {seed}: bearish absorption must sit at a high"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


def test_cvd_flow_never_exceeds_its_volume_bar() -> None:
    """Credibility of generated order flow: a bar's signed flow cannot exceed the volume that bar
    traded. Each CVD step is `volume x imbalance ratio` by construction — this asserts the rendered,
    rounded payload still honours it, so the pane (and the dev CSV export) can never show impossible
    flow. Also checks the line is genuinely CUMULATIVE — it accumulates rather than jittering."""
    for label in _CVD_LABELS:
        config = _config("cvd_divergence", [label], list(_CVD_LABELS))
        for seed in range(20):
            _lbl, _ann, payload = _instantiate(config, seed)  # type: ignore[arg-type]
            cvd = np.asarray(payload["cvd"], dtype=float)  # type: ignore[index]
            volume = np.asarray(payload["series"]["volume"], dtype=float)  # type: ignore[index]
            steps = np.abs(np.diff(cvd))
            worst = float(np.max(steps / volume[1:]))
            assert worst <= 0.79, f"{label}/{seed}: a bar moved CVD by {worst:.2f}x its own volume"
            # An accumulating line spans many times its largest single step; pure bar-to-bar jitter
            # would sit near 1-2. Vetting over 3600 charts (300 seeds x n in 110..150) put the floor
            # at 4.06, so 2.5 flags a broken construction without tracking the noise.
            span = float(np.max(cvd) - np.min(cvd))
            assert span > 2.5 * float(np.max(steps)), (
                f"{label}/{seed}: CVD jitters instead of accumulating (span {span:.0f})"
            )


# --- candle_reaction (m08-l2) correctness: form + location match the label -----------------------


def _reaction_extremes(payload: dict) -> tuple[float, float, float]:
    """Over the last 3 visible candles: max |body|/close, max wick/close, and whether a level exists."""
    s = payload["series"]
    n = len(s["close"])
    max_body = max_wick = 0.0
    for j in range(n - 3, n):
        o, high, low, c = s["open"][j], s["high"][j], s["low"][j], s["close"][j]
        body = abs(c - o)
        max_body = max(max_body, body / c)
        max_wick = max(max_wick, (high - low - body) / c)
    return max_body, max_wick, float(len(payload["levels"]))


_REACTION_LABELS = ("rejection_at_level", "overrun_at_level", "open_space", "indecision")


def test_candle_reaction_form_and_location_match_label() -> None:
    seen: dict[str, int] = dict.fromkeys(_REACTION_LABELS, 0)
    for label in seen:
        cfg = _config("candle_reaction", [label], list(seen))
        levels = wicks = bodies = 0
        for seed in range(24):
            _lbl, _ann, payload = _instantiate(cfg, seed)  # type: ignore[arg-type]
            body, wick, has_level = _reaction_extremes(payload)  # type: ignore[arg-type]
            levels += 1 if has_level else 0
            wicks += 1 if wick > 0.02 else 0
            bodies += 1 if body > 0.02 else 0
            seen[label] += 1
        if label in ("rejection_at_level", "overrun_at_level"):
            assert levels == 24, f"{label}: a level must be drawn ({levels}/24)"
        else:
            assert levels == 0, f"{label}: no level in open space / indecision ({levels}/24)"
        if label == "rejection_at_level":
            assert wicks == 24, "rejection must show a long wick"
            assert bodies == 0, "rejection is a small body, not an overrun"
        if label == "overrun_at_level":
            assert bodies == 24, "overrun must show an engulfing body"
        if label == "indecision":
            assert bodies == 0, "indecision is a tiny body (doji / small range)"
    assert all(v > 0 for v in seen.values()), f"not all labels surfaced: {seen}"


# --- the four figure-only injectors ---------------------------------------------------------------
#
# `market_structure` (m08-l1), `liquidity_sweep` (m17-l2 + m06-l1), `stop_limit_gap` (m21-l1) and
# `trade_anatomy` (m24-l1) get the same treatment as everything above — the credibility test at the top
# of this file is parametrised over every registered injector, so it already covers them — but their
# structure-matches-label tests live in `test_chart_annotations.py` instead of here.
#
# That is not an exception, it is where the claim is: each of them plants a MARKED feature (the labelled
# pivot, the sweep bar, the slice candle, the rejection wick) and draws lines pinned to it, so "does the
# geometry encode the label" and "does the annotation match the geometry" are one question for them and
# asking it twice in two files would let the two answers drift apart.
