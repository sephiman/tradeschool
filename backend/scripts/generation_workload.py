# SPDX-License-Identifier: AGPL-3.0-only
"""The generation path's contract workload, defined once for every script that sweeps it.

`measure_libm_parity.py` records what reaches `np.exp`/`np.log`, `verify_golden_stability.py` hashes
what comes out; both must sweep the same path, so the seed list, the configs and the figure panels
live here only. Two modes, because the generators have two: EXERCISE (`_instantiate`, resolution off
screen) and FIGURE (`build_figure`, resolution appended plus its three recompute hooks).

Run as a module to print the workload's shape.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

# `tradeschool` importable whether or not the project is pip-installed; `tests/` too, because the
# golden suite is where a fingerprint is DEFINED and a second copy of the recipe would drift.
_BACKEND = Path(__file__).resolve().parent.parent
for _extra in (_BACKEND / "src", _BACKEND / "tests"):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from test_golden_exercise_mode import _fp as fingerprint  # type: ignore[import-not-found]  # noqa: E402
from tradeschool.content.schema import LocalizedText  # noqa: E402
from tradeschool.exercises.charts.patterns.registry import all_injectors  # noqa: E402
from tradeschool.exercises.charts.types import DivergenceType  # noqa: E402
from tradeschool.exercises.figures import (  # noqa: E402
    FigurePanel,
    FigureSpec,
    build_figure,
    load_figures,
)
from tradeschool.exercises.pattern_chart import PatternChartGenerator  # noqa: E402
from tradeschool.exercises.pattern_chart import _instantiate as pattern_instantiate  # noqa: E402
from tradeschool.exercises.synthetic_chart import SyntheticChartGenerator  # noqa: E402
from tradeschool.exercises.synthetic_chart import _instantiate as divergence_instantiate  # noqa: E402

#: The repo's `content/` tree, for the frozen figure specs (the backend sits one level below it).
CONTENT_DIR = _BACKEND.parent / "content"

#: Probe seeds, fixed forever. A range, not a hand-picked list: the generators are seed-deterministic,
#: so consecutive seeds are as independent as scattered ones.
PROBE_SEEDS: tuple[int, ...] = tuple(range(50))

#: Bars per generated chart. The golden fingerprints use 130 and the figure default is 160; the sweep
#: uses the SHORTER one for exercise mode (matching the goldens) and each figure's own `n`.
EXERCISE_BARS = 130

#: The one injector outside the pattern registry. Both oscillators are swept: the MACD branch takes a
#: different retry path, so it reaches `np.exp` a different number of times.
DIVERGENCE_INDICATORS = ("rsi", "macd")
DIVERGENCE_TARGETS = tuple(t.value for t in DivergenceType)

#: The three targets the COMMITTED goldens use, swept as its own config beside the five-target one.
#: Not redundant: the target is drawn with `rng.integers(0, len(targets))`, so this list's LENGTH
#: decides each seed's label. Without it the four `divergence:*` golden documents fall outside the
#: sweep — measured, 80/84 before and 84/84 after.
GOLDEN_DIVERGENCE_TARGETS = ("none", "bullish_regular", "bearish_regular")


@dataclass(frozen=True)
class WorkItem:
    """One generated document: `key` names it, `run` produces it (or raises)."""

    mode: str  # "exercise" | "figure"
    key: str
    run: Callable[[], object]


def pattern_config(injector_name: str, labels: tuple[str, ...], targets: list[str]) -> object:
    return PatternChartGenerator().parse_config(
        {
            "type": "pattern_chart",
            "prompt": {"en": "x", "es": "x"},
            "injector": injector_name,
            "n": EXERCISE_BARS,
            "targets": targets,
            "choices": list(labels),
        }
    )


def divergence_config(indicator: str, targets: tuple[str, ...] = DIVERGENCE_TARGETS) -> object:
    return SyntheticChartGenerator().parse_config(
        {
            "type": "synthetic_chart",
            "prompt": {"en": "x", "es": "x"},
            "indicator": indicator,
            "n": 120,
            "targets": list(targets),
            "choices": list(targets),
        }
    )


def iter_exercise_items(seeds: tuple[int, ...] = PROBE_SEEDS) -> Iterator[WorkItem]:
    """Exercise mode: every injector plus the divergence generator, over `seeds`.

    Two configs each — MULTI-target (the goldens' own, where the draw picks a label) and one
    SINGLE-target per label (deterministic draw, so no label goes unswept).
    """
    for inj in all_injectors():
        labels = tuple(inj.labels)
        multi = pattern_config(inj.name, labels, list(labels))
        for seed in seeds:
            yield WorkItem(
                "exercise",
                f"{inj.name}:multi:{seed}",
                lambda c=multi, s=seed: pattern_instantiate(c, s),  # type: ignore[misc]
            )
        for label in labels:
            single = pattern_config(inj.name, labels, [label])
            for seed in seeds:
                yield WorkItem(
                    "exercise",
                    f"{inj.name}:{label}:{seed}",
                    lambda c=single, s=seed: pattern_instantiate(c, s),  # type: ignore[misc]
                )

    # Two target lists per oscillator: the draw depends on `len(targets)`, so a different list is a
    # different document, not a subset.
    for indicator in DIVERGENCE_INDICATORS:
        for shape, targets in (("multi", DIVERGENCE_TARGETS), ("golden", GOLDEN_DIVERGENCE_TARGETS)):
            cfg = divergence_config(indicator, targets)
            for seed in seeds:
                yield WorkItem(
                    "exercise",
                    f"divergence:{indicator}:{shape}:{seed}",
                    lambda c=cfg, s=seed: divergence_instantiate(c, s),  # type: ignore[misc]
                )


def _synth_spec(panel: FigurePanel, key: str) -> FigureSpec:
    return FigureSpec(
        id=key, caption=LocalizedText(en="x", es="x"), panels=[panel]
    )


def iter_figure_items(seeds: tuple[int, ...] = PROBE_SEEDS) -> Iterator[WorkItem]:
    """Figure mode: every injector and label over `seeds`, plus every FROZEN content figure.

    The synthesized panels make this a sweep rather than a spot check; the frozen ones are the figures
    that actually ship.
    """
    for inj in all_injectors():
        for label in inj.labels:
            for seed in seeds:
                key = f"{inj.name}:{label}:{seed}"
                panel = FigurePanel(
                    generator="pattern_chart", injector=inj.name, target=label, seed=seed
                )
                spec = _synth_spec(panel, f"fig-{key}")
                yield WorkItem("figure", key, lambda sp=spec: build_figure(sp, "en"))  # type: ignore[misc]

    for target in DIVERGENCE_TARGETS:
        for indicator in DIVERGENCE_INDICATORS:
            for seed in seeds:
                key = f"divergence:{indicator}:{target}:{seed}"
                panel = FigurePanel(
                    generator="synthetic_chart", target=target, seed=seed, indicator=indicator
                )
                spec = _synth_spec(panel, f"fig-{key}")
                yield WorkItem("figure", key, lambda sp=spec: build_figure(sp, "en"))  # type: ignore[misc]

    for fig_id, spec in sorted(load_figures(CONTENT_DIR).items()):
        if spec.kind != "chart":
            continue  # an `svg` figure is a frontend component name, not generated numerics
        yield WorkItem("figure", f"frozen:{fig_id}", lambda sp=spec: build_figure(sp, "en"))  # type: ignore[misc]


def iter_all_items(seeds: tuple[int, ...] = PROBE_SEEDS) -> Iterator[WorkItem]:
    yield from iter_exercise_items(seeds)
    yield from iter_figure_items(seeds)


@dataclass
class RunReport:
    """What a sweep did: how many documents were produced, and every one that refused to build."""

    produced: int = 0
    failures: list[tuple[str, str, str]] = field(default_factory=list)


def run_workload(
    seeds: tuple[int, ...] = PROBE_SEEDS,
    *,
    sink: Callable[[WorkItem, object], None] | None = None,
    quiet: bool = False,
) -> RunReport:
    """Build every document; `sink(item, result)` sees each one.

    A refusal is recorded and the sweep continues — stopping at the first would measure a fraction of
    the path.
    """
    report = RunReport()
    for item in iter_all_items(seeds):
        try:
            result = item.run()
        except Exception as exc:
            report.failures.append((item.mode, item.key, f"{type(exc).__name__}: {exc}"))
            continue
        report.produced += 1
        if sink is not None:
            sink(item, result)
        if not quiet and report.produced % 500 == 0:
            print(f"  ... {report.produced} documents", flush=True)
    return report


def _jsonable(value: object) -> object:
    """Flatten a document to JSON primitives, so one recipe fingerprints all three return shapes."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple | list):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def fingerprints(seeds: tuple[int, ...] = PROBE_SEEDS, *, quiet: bool = True) -> dict[str, str]:
    """`mode:key -> fingerprint` for every document, using the golden suite's recipe.

    A refusal is recorded as `"REFUSED"`, not dropped: a refusal that starts or stops happening is
    itself a change.
    """
    out: dict[str, str] = {}

    def sink(item: WorkItem, result: object) -> None:
        out[f"{item.mode}:{item.key}"] = fingerprint(_jsonable(result))

    report = run_workload(seeds, sink=sink, quiet=quiet)
    for mode, key, _reason in report.failures:
        out[f"{mode}:{key}"] = "REFUSED"
    return out


def main() -> int:
    exercise = sum(1 for _ in iter_exercise_items())
    figure = sum(1 for _ in iter_figure_items())
    print(f"probe seeds:        {len(PROBE_SEEDS)} ({PROBE_SEEDS[0]}..{PROBE_SEEDS[-1]})")
    print(f"injectors:          {len(all_injectors())} pattern + 1 divergence")
    print(f"exercise documents: {exercise}")
    print(f"figure documents:   {figure}")
    print(f"total:              {exercise + figure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
