# SPDX-License-Identifier: AGPL-3.0-only
"""Pydantic schema for `course.yaml` (the manifest) plus structural validation.

The canonical structure and order; prose and generator configs live elsewhere, loaded by the registry.
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


class KeyedEntity(BaseModel):
    """An entity with a display id and a permanent `key` (defaults to the id at creation).

    The key is chosen once and NEVER renamed: seeds, stored progress and glossary origins hang off
    it, so display ids can be reorganized without a data migration. See content/README.md.
    """

    id: str
    key: str = ""

    @model_validator(mode="after")
    def _default_key(self) -> Self:
        if not self.key:
            self.key = self.id
        return self


class ManifestExercise(KeyedEntity):
    model_config = ConfigDict(extra="forbid")
    type: ExerciseType


class ManifestLesson(KeyedEntity):
    model_config = ConfigDict(extra="forbid")
    title: LocalizedText
    exercises: list[ManifestExercise] = Field(default_factory=list)


class ManifestModule(KeyedEntity):
    model_config = ConfigDict(extra="forbid")
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
    """The root course entity; its blocks live at the manifest's top level."""

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

        # Keys form their own global namespace (course and block ids double as their keys). Ids and
        # keys may overlap in VALUE across entities — the 2026-08-10 renumbering reused the id range —
        # so the two sets are checked apart, never merged.
        seen_keys: set[str] = set()
        for level in (
            [self.course.id],
            [b.id for b in self.blocks],
            [m.key for _, m in self.iter_modules()],
            [lesson.key for _, lesson in self.iter_lessons()],
            [ex.key for _, _, ex in self.iter_exercises()],
        ):
            for key in level:
                if key in seen_keys:
                    raise ValueError(f"duplicate stable key: {key!r}")
                seen_keys.add(key)

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
