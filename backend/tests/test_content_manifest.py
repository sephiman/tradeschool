# SPDX-License-Identifier: AGPL-3.0-only
"""Validation of the real manifest and of the structural rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tradeschool.config import get_settings
from tradeschool.content.registry import load_registry
from tradeschool.content.schema import (
    LocalizedText,
    Manifest,
    ManifestBlock,
    ManifestCourse,
    ManifestModule,
)


def _t(s: str) -> LocalizedText:
    return LocalizedText(en=s, es=s)


def _course() -> ManifestCourse:
    return ManifestCourse(id="c1", title=_t("Course"), description=_t("desc"))


def test_real_manifest_loads_and_lessons_have_both_languages() -> None:
    registry = load_registry(get_settings().content_dir)
    # The single course today owns all existing content under a stable id.
    assert registry.manifest.course.id == "crypto-futures"
    assert registry.manifest.course.title.en and registry.manifest.course.description.es
    # 23 modules across 5 blocks.
    assert len(registry.manifest.blocks) == 5
    assert len(registry.manifest.iter_modules()) == 23
    # Every authored lesson exists in both languages (load_registry enforces it).
    for locale in ("en", "es"):
        assert "m06-l1" in registry.markdown[locale]


def test_all_phase1_exercises_are_playable() -> None:
    # Every exercise declared in the manifest must have a valid, loaded generator config.
    registry = load_registry(get_settings().content_dir)
    for _, _, exercise in registry.manifest.iter_exercises():
        assert registry.get_exercise_config(exercise.id) is not None, f"{exercise.id} not playable"


def test_duplicate_ids_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate stable id"):
        Manifest(
            course=_course(),
            blocks=[
                ManifestBlock(
                    id="b1",
                    title=_t("b"),
                    modules=[
                        ManifestModule(id="dup", title=_t("x"), summary=_t("x")),
                        ManifestModule(id="dup", title=_t("y"), summary=_t("y")),
                    ],
                )
            ],
        )


def test_unknown_assumes_rejected() -> None:
    with pytest.raises(ValidationError, match="unknown module"):
        Manifest(
            course=_course(),
            blocks=[
                ManifestBlock(
                    id="b1",
                    title=_t("b"),
                    modules=[ManifestModule(id="m", title=_t("m"), summary=_t("m"), assumes=["ghost"])],
                )
            ],
        )
