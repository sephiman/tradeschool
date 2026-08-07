# SPDX-License-Identifier: AGPL-3.0-only
"""Generator registry (§3.2): one implementation per type. Adding a type is a new entry, not a change."""

from __future__ import annotations

from tradeschool.exercises.base import ExerciseGenerator
from tradeschool.exercises.calculation import CalculationGenerator
from tradeschool.exercises.fixture_chart import FixtureChartGenerator
from tradeschool.exercises.pattern_chart import PatternChartGenerator
from tradeschool.exercises.quiz import QuizGenerator
from tradeschool.exercises.synthetic_chart import SyntheticChartGenerator
from tradeschool.exercises.types import ExerciseType

_GENERATORS: dict[ExerciseType, ExerciseGenerator] = {
    generator.type: generator
    for generator in (
        QuizGenerator(),
        CalculationGenerator(),
        SyntheticChartGenerator(),
        FixtureChartGenerator(),
        PatternChartGenerator(),
    )
}


def has_generator(exercise_type: ExerciseType) -> bool:
    return exercise_type in _GENERATORS


def get_generator(exercise_type: ExerciseType) -> ExerciseGenerator:
    try:
        return _GENERATORS[exercise_type]
    except KeyError as exc:
        raise KeyError(f"no generator registered for {exercise_type.value!r}") from exc
