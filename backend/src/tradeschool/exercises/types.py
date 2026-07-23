# SPDX-License-Identifier: AGPL-3.0-only
"""The exercise-type taxonomy, shared by the content model and the generator registry."""

from __future__ import annotations

from enum import StrEnum


class ExerciseType(StrEnum):
    QUIZ = "quiz"
    CALCULATION = "calculation"
    SYNTHETIC_CHART = "synthetic_chart"
    FIXTURE_CHART = "fixture_chart"
    # Phase 2: generic chart generator hosting the pluggable pattern injectors (fakeouts, Wyckoff,
    # moving averages, oscillator readings, Fibonacci, volume, derivatives). The frozen
    # SYNTHETIC_CHART stays divergence-only; new injectors are additions on this type (§ freeze rule).
    PATTERN_CHART = "pattern_chart"
