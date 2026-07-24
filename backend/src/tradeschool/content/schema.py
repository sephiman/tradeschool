# SPDX-License-Identifier: AGPL-3.0-only
"""Pydantic schema for `course.yaml` (the manifest) plus structural validation.

The manifest is the canonical structure: blocks → modules → lessons → exercises, the canonical
order (list position), advisory prerequisites (`assumes`), and localized labels. Lesson prose and
generator configs live elsewhere (content trees / exercise files) and are loaded by the registry.
"""

from __future__ import annotations

from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradeschool.exercises.types import ExerciseType

LOCALES = ("en", "es")


class LocalizedText(BaseModel):
    model_config = ConfigDict(extra="forbid")
    en: str
    es: str

    def get(self, locale: str) -> str:
        return self.es if locale == "es" else self.en


class ManifestExercise(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    type: ExerciseType


class ManifestLesson(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: LocalizedText
    exercises: list[ManifestExercise] = Field(default_factory=list)


class ManifestModule(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: LocalizedText
    summary: LocalizedText
    assumes: list[str] = Field(default_factory=list)
    lessons: list[ManifestLesson] = Field(default_factory=list)


class ManifestBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    title: LocalizedText
    modules: list[ManifestModule] = Field(default_factory=list)


class ManifestCourse(BaseModel):
    """The root course entity. Its blocks live at the manifest's top level (a single course today;
    the structure is ready for more). Also the data source for the course-page header."""

    model_config = ConfigDict(extra="forbid")
    id: str
    title: LocalizedText
    description: LocalizedText


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    course: ManifestCourse
    blocks: list[ManifestBlock]

    # --- Derived views ---
    def iter_modules(self) -> list[tuple[ManifestBlock, ManifestModule]]:
        return [(b, m) for b in self.blocks for m in b.modules]

    def iter_lessons(self) -> list[tuple[ManifestModule, ManifestLesson]]:
        return [(m, lesson) for _, m in self.iter_modules() for lesson in m.lessons]

    def iter_exercises(self) -> list[tuple[ManifestModule, ManifestLesson, ManifestExercise]]:
        return [
            (m, lesson, ex)
            for m, lesson in self.iter_lessons()
            for ex in lesson.exercises
        ]

    def module_ids(self) -> set[str]:
        return {m.id for _, m in self.iter_modules()}

    @model_validator(mode="after")
    def _validate_structure(self) -> Self:
        seen: set[str] = set()
        # IDs are globally unique across every level, course id included — a future course must
        # namespace its ids (e.g. spot-m01); see content/README.md.
        for level in (
            [self.course.id],
            [b.id for b in self.blocks],
            [m.id for _, m in self.iter_modules()],
            [lesson.id for _, lesson in self.iter_lessons()],
            [ex.id for _, _, ex in self.iter_exercises()],
        ):
            for identifier in level:
                if identifier in seen:
                    raise ValueError(f"duplicate stable id: {identifier!r}")
                seen.add(identifier)

        module_ids = self.module_ids()
        for _, module in self.iter_modules():
            for dep in module.assumes:
                if dep not in module_ids:
                    raise ValueError(
                        f"module {module.id!r} assumes unknown module {dep!r}"
                    )
                if dep == module.id:
                    raise ValueError(f"module {module.id!r} cannot assume itself")
        return self


def parse_manifest(path: Path) -> Manifest:
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return Manifest.model_validate(raw)
