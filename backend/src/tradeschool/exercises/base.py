# SPDX-License-Identifier: AGPL-3.0-only
"""The ExerciseGenerator contract (§3.2).

Generators are pure, seed-deterministic functions: `(config, seed) -> instance`. The same seed
always reproduces the same instance and the same grading, so any past attempt is exactly
replayable from its stored seed. A generator never leaks the solution in `generate`; the solution
is produced only by `grade`, after the learner has answered (§3.1).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import ClassVar

from pydantic import BaseModel

from tradeschool.exercises.types import ExerciseType


class InvalidAnswerError(Exception):
    """The submitted answer is malformed for this exercise type."""


@dataclass
class GeneratedInstance:
    """The public view of an instantiated exercise — statement + display data, never the solution."""

    prompt: str
    payload: dict[str, object] = field(default_factory=dict)


@dataclass
class GradeResult:
    """Returned only after answering: correctness plus the instantiated step-by-step solution."""

    correct: bool
    correct_answer: object
    solution_steps: list[str] = field(default_factory=list)
    explanation: str | None = None


def rng_for(seed: int) -> random.Random:
    """The single source of seed-determinism shared by all generators."""
    return random.Random(seed)


class ExerciseGenerator(ABC):
    type: ClassVar[ExerciseType]

    @abstractmethod
    def parse_config(self, raw: Mapping[str, object]) -> BaseModel:
        """Validate and parse a raw exercise config; raises on malformed content."""

    @abstractmethod
    def generate(self, config: BaseModel, seed: int, locale: str) -> GeneratedInstance:
        """Instantiate the exercise for display. Must NOT include the solution."""

    @abstractmethod
    def grade(
        self, config: BaseModel, seed: int, answer: Mapping[str, object], locale: str
    ) -> GradeResult:
        """Evaluate an answer against the seed-instantiated scenario; returns the solution."""
