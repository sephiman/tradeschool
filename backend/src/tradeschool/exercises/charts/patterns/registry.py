# SPDX-License-Identifier: AGPL-3.0-only
"""Pattern-injector registry (the house-connector pattern §3.2): one injector per `name`. Adding a
Phase-2 injector is a new entry here plus its module — never a change to the frozen generators."""

from __future__ import annotations

from tradeschool.exercises.charts.patterns.base import PatternInjector
from tradeschool.exercises.charts.patterns.candle_reaction import CandleReactionInjector
from tradeschool.exercises.charts.patterns.derivatives import DerivativesInjector
from tradeschool.exercises.charts.patterns.fakeout import FakeoutInjector
from tradeschool.exercises.charts.patterns.fibonacci import FibonacciInjector
from tradeschool.exercises.charts.patterns.ma_context import MaContextInjector
from tradeschool.exercises.charts.patterns.oscillator_reading import OscillatorReadingInjector
from tradeschool.exercises.charts.patterns.volume_confirmation import VolumeConfirmationInjector
from tradeschool.exercises.charts.patterns.wyckoff import WyckoffInjector

_INJECTORS: dict[str, PatternInjector] = {
    injector.name: injector
    for injector in (
        FakeoutInjector(),
        MaContextInjector(),
        OscillatorReadingInjector(),
        FibonacciInjector(),
        VolumeConfirmationInjector(),
        WyckoffInjector(),
        DerivativesInjector(),
        CandleReactionInjector(),
    )
}


def has_injector(name: str) -> bool:
    return name in _INJECTORS


def get_injector(name: str) -> PatternInjector:
    try:
        return _INJECTORS[name]
    except KeyError as exc:
        raise KeyError(f"no pattern injector registered for {name!r}") from exc


def all_injectors() -> list[PatternInjector]:
    return list(_INJECTORS.values())
