# SPDX-License-Identifier: AGPL-3.0-only
"""The lessons' worked numbers are approximations of their figures' generated values.

The FIGURE is the source of truth and the prose rounds it, which couples prose to generator output: a
reseed silently strands every number beside the chart, and nothing crashes.
`content/figure-coupling.yaml` declares the coupling; this checks it both ways — the figure moved, and
the prose moved (per-locale number formatting, both content trees). `identical_through` holds
same-seed panels equal bar by bar, and guarded exceptions must keep their generated-instance lead-in.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tradeschool.exercises.figures import build_figure, load_figures

CONTENT = Path(__file__).resolve().parents[2] / "content"
MANIFEST = CONTENT / "figure-coupling.yaml"
LOCALES = ("es", "en")
_DEFAULT_TOL = 0.01  # a human rounding lands well inside 1%; a moved figure lands well outside it

_SERIES_KEYS = ("open", "high", "low", "close", "volume")
_PANE_KEYS = ("rsi", "oi", "cvd")


def _manifest() -> dict[str, Any]:
    with MANIFEST.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    assert isinstance(raw, dict)
    return raw


_MANIFEST = _manifest()
_FIGURES = load_figures(CONTENT)
_COUPLED: dict[str, Any] = _MANIFEST["figures"]
_EXCEPTIONS: dict[str, Any] = _MANIFEST["exceptions"]


def _built(figure_id: str) -> dict[str, Any]:
    return build_figure(_FIGURES[figure_id], "en")


def _panel(figure_id: str, index: int) -> dict[str, Any]:
    panels = _built(figure_id)["panels"]
    assert isinstance(panels, list)
    panel = panels[index]
    assert isinstance(panel, dict)
    return panel


def _lesson_text(lesson_id: str, locale: str) -> str:
    return (CONTENT / locale / "lessons" / f"{lesson_id}.md").read_text(encoding="utf-8")


def _resolve(panel: dict[str, Any], what: str, spec: dict[str, Any]) -> float:
    """Turn an anchor's `what` expression into the figure's actual number."""
    kind, _, arg = what.partition(":")
    series = panel["series"]

    if kind == "level":
        for level in panel["levels"]:
            if level["label"] == arg:
                return float(level["price"])
        raise AssertionError(f"no level labelled {arg!r} (has: {[x['label'] for x in panel['levels']]})")
    if kind in ("band_low", "band_high"):
        # A zone has two prices and a lesson quotes both, so each edge is its own anchor (m30's origin
        # zone and imbalance). The edges are derived from the CANDLES the injector planted — a down-leg's
        # range, a pair of wicks either side of a one-bar move — so they move if the generator moves,
        # which is exactly what this manifest exists to catch.
        for band in panel["bands"]:
            if band["label"] == arg:
                return float(band["low" if kind == "band_low" else "high"])
        raise AssertionError(f"no band labelled {arg!r} (has: {[x['label'] for x in panel['bands']]})")
    if kind in _SERIES_KEYS:
        return float(series[kind][int(arg)])
    if kind in _PANE_KEYS:
        assert kind in panel, f"figure has no {kind} pane"
        return float(panel[kind][int(arg)])
    if kind == "volume_ratio":
        lo, hi = (int(x) for x in arg.split("-"))
        b_lo, b_hi = spec["volume_baseline"]
        return _median(series["volume"][lo:hi]) / _median(series["volume"][b_lo:b_hi])
    if kind in ("fib_impulse_low", "fib_impulse_high"):
        levels = {level["label"]: float(level["price"]) for level in panel["levels"]}
        span = (levels["500"] - levels["618"]) / (0.618 - 0.5)
        high = levels["500"] + span / 2
        return high if kind == "fib_impulse_high" else high - span
    raise AssertionError(f"unknown anchor expression {what!r}")


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    mid = len(ordered) // 2
    return ordered[mid] if len(ordered) % 2 else (ordered[mid - 1] + ordered[mid]) / 2


def _localized(number: float, locale: str) -> str:
    """How each tree writes a coupled number: 1.800 in Spanish, 1,800 in English."""
    grouped = f"{abs(int(number)):,}"
    return grouped.replace(",", ".") if locale == "es" else grouped


def _anchors() -> list[tuple[str, dict[str, Any], dict[str, Any]]]:
    return [(fid, spec, anchor) for fid, spec in _COUPLED.items() for anchor in spec["anchors"]]


def _ident(figure_id: str, anchor: dict[str, Any]) -> str:
    return f"{figure_id}[panel {anchor.get('panel', 0)}] {anchor['what']}"


# --- the manifest describes reality ---------------------------------------------------------------


@pytest.mark.parametrize("figure_id", sorted({*_COUPLED, *_EXCEPTIONS}))
def test_every_declared_figure_exists_and_its_lessons_embed_it(figure_id: str) -> None:
    assert figure_id in _FIGURES, f"figure-coupling.yaml names an unknown figure {figure_id!r}"
    spec = _COUPLED.get(figure_id) or _EXCEPTIONS[figure_id]
    directive = f"::figure{{id={figure_id}}}"
    for lesson_id in spec["lessons"]:
        for locale in LOCALES:
            body = _lesson_text(lesson_id, locale)
            assert directive in body, f"{locale}/{lesson_id} does not embed {figure_id}"


# --- 1. the figure has not moved out from under the prose -----------------------------------------


@pytest.mark.parametrize(
    ("figure_id", "spec", "anchor"), _anchors(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_prose_number_still_approximates_the_generated_value(
    figure_id: str, spec: dict[str, Any], anchor: dict[str, Any]
) -> None:
    panel = _panel(figure_id, anchor.get("panel", 0))
    actual = _resolve(panel, anchor["what"], spec)
    stale = (
        f"{_ident(figure_id, anchor)} is now {actual:.2f}. The figure moved out from under the prose "
        f"— re-run the worked-number pass for: {', '.join(spec['lessons'])} (es + en), then update "
        f"content/figure-coupling.yaml."
    )

    if "min" in anchor or "max" in anchor:
        assert anchor["min"] <= actual <= anchor["max"], (
            f"{stale} It left the band [{anchor['min']}, {anchor['max']}] the prose's qualitative "
            f"claim depends on."
        )
        return

    prose = float(anchor["prose"])
    if "abstol" in anchor:
        assert abs(actual - prose) <= anchor["abstol"], f"{stale} The prose says {anchor['prose']}."
    else:
        tol = float(anchor.get("tol", _DEFAULT_TOL))
        assert abs(actual - prose) <= tol * abs(actual), (
            f"{stale} The prose says {anchor['prose']}, which is "
            f"{abs(actual - prose) / abs(actual):.2%} off (tolerance {tol:.0%})."
        )


# --- 2. the prose still prints the number it is pinned to -----------------------------------------


@pytest.mark.parametrize(
    ("figure_id", "spec", "anchor"), _anchors(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_coupled_number_appears_in_every_lesson_that_quotes_it(
    figure_id: str, spec: dict[str, Any], anchor: dict[str, Any]
) -> None:
    if not anchor.get("in_prose", True) or "prose" not in anchor:
        pytest.skip("value-checked only: too small a number to search for meaningfully")
    # An anchor may narrow the figure's lesson list: two lessons can embed one figure and quote
    # different amounts of it (m09-l1 is the map and prints the support and the spring; m09-l2 walks
    # every phase), and demanding the whole chart from the lesson that needs two numbers would push
    # the other five into it just to satisfy a test.
    for lesson_id in anchor.get("lessons", spec["lessons"]):
        for locale in LOCALES:
            wanted = _localized(float(anchor["prose"]), locale)
            body = _lesson_text(lesson_id, locale)
            # Bounded so 2.125 does not match inside 2.1250 or 2.125,50 — but a number ending a
            # sentence ("...se queda en 29.350.") still counts, so the trailing separator is only
            # rejected when a digit follows it.
            assert re.search(rf"(?<![\d.,]){re.escape(wanted)}(?!\d)(?![.,]\d)", body), (
                f"{locale}/{lesson_id} no longer prints {wanted}, the rounded value of "
                f"{_ident(figure_id, anchor)}. Either the prose drifted from the figure or the "
                f"coupling in content/figure-coupling.yaml is out of date."
            )


# --- 3. panels the prose calls "the same chart" are the same chart --------------------------------


@pytest.mark.parametrize(
    "figure_id", sorted(fid for fid, spec in _COUPLED.items() if "identical_through" in spec)
)
def test_panels_that_share_a_seed_render_the_same_candles(figure_id: str) -> None:
    spec = _COUPLED[figure_id]
    through = spec["identical_through"]
    first = _panel(figure_id, 0)["series"]
    for index in range(1, len(_built(figure_id)["panels"])):
        other = _panel(figure_id, index)["series"]
        for key in ("open", "high", "low", "close"):
            assert first[key][: through + 1] == other[key][: through + 1], (
                f"{figure_id}: panels 0 and {index} diverge in {key} before bar {through}, but "
                f"{', '.join(spec['lessons'])} tell the reader they are the same chart. Either the "
                f"panels stopped sharing a seed or the claim has to come out of the prose."
            )


# --- 4. figures the prose does NOT adapt to keep their lead-in ------------------------------------


@pytest.mark.parametrize("figure_id", sorted(_EXCEPTIONS))
def test_exception_figures_keep_their_generated_instance_lead_in(figure_id: str) -> None:
    spec = _EXCEPTIONS[figure_id]
    for lesson_id in spec["lessons"]:
        for locale in LOCALES:
            phrase = spec["guard_phrase"][locale]
            body = _lesson_text(lesson_id, locale)
            assert phrase.lower() in body.lower(), (
                f"{locale}/{lesson_id} lost the '{phrase}' lead-in for {figure_id}. That figure is a "
                f"declared exception — its prose keeps its own numbers — so the reader has to be told "
                f"the chart carries different ones. Reason on file: {spec['why'].strip()}"
            )
