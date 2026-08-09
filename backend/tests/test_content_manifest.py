# SPDX-License-Identifier: AGPL-3.0-only
"""Validation of the real manifest and of the structural rules."""

from __future__ import annotations

import re

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

_FIGURE_REF = re.compile(r"::figure\{id=([^}\s]+)\}")
# Injectors that exist only to draw lesson figures. A figure SHOWS the resolution; an exercise must cut
# before it, so an exercise built on one of these would hand over its own answer.
_FIGURE_ONLY_INJECTORS = {"market_structure", "liquidity_sweep", "stop_limit_gap", "trade_anatomy"}


def _t(s: str) -> LocalizedText:
    return LocalizedText(en=s, es=s)


def _course() -> ManifestCourse:
    return ManifestCourse(id="c1", title=_t("Course"), description=_t("desc"))


def test_real_manifest_loads_and_lessons_have_both_languages() -> None:
    registry = load_registry(get_settings().content_dir)
    # The single course today owns all existing content under a stable id.
    assert registry.manifest.course.id == "crypto-futures"
    assert registry.manifest.course.title.en and registry.manifest.course.description.es
    # 34 modules across 7 blocks. Block G is still the trailing single-module block (m30, the SMC
    # dialect); the id says when a module was written and the position says where it belongs, and
    # content/README.md allows the two to disagree.
    assert len(registry.manifest.blocks) == 7
    assert len(registry.manifest.iter_modules()) == 34
    block_c = next(b for b in registry.manifest.blocks if b.id == "block-c")
    assert [m.id for m in block_c.modules][-3:] == ["m14", "m31", "m32"]
    # m33 and m34 are INSERTED rather than appended, which the README allows only where the position is
    # load-bearing — pinned here so a stray reorder is a failing test rather than a silent regression.
    # m33 tests the claim m22 makes and is pointed back at by m23 and m24; m34 inhabits the arbitrage
    # m17-l1 mentions in passing.
    block_d = next(b for b in registry.manifest.blocks if b.id == "block-d")
    block_e = next(b for b in registry.manifest.blocks if b.id == "block-e")
    assert [m.id for m in block_d.modules] == ["m15", "m16", "m17", "m34", "m18"]
    assert [m.id for m in block_e.modules] == ["m19", "m20", "m21", "m22", "m33", "m23", "m24"]
    # Every authored lesson exists in both languages (load_registry enforces it).
    for locale in ("en", "es"):
        assert "m06-l1" in registry.markdown[locale]


def test_every_exercise_resolves_to_the_lesson_it_lives_on() -> None:
    """Every exercise resolves to its LESSON — the `m08-ex-5` → `m08` prefix is wrong for half of m08."""
    registry = load_registry(get_settings().content_dir)
    for _, lesson, exercise in registry.manifest.iter_exercises():
        assert registry.exercise_lesson_id(exercise.id) == lesson.id
    assert registry.exercise_lesson_id("m08-ex-1") == "m08-l1"
    assert registry.exercise_lesson_id("m08-ex-5") == "m08-l2"
    assert registry.exercise_lesson_id("nope-ex-1") is None


def test_all_phase1_exercises_are_playable() -> None:
    # Every exercise declared in the manifest must have a valid, loaded generator config.
    registry = load_registry(get_settings().content_dir)
    for _, _, exercise in registry.manifest.iter_exercises():
        assert registry.get_exercise_config(exercise.id) is not None, f"{exercise.id} not playable"


def test_every_figure_reference_resolves_and_no_spec_is_orphaned() -> None:
    """Both directions: every `::figure` reference resolves to a spec, and every spec is referenced.

    A directive is a plain string in prose, so a typo produces a permanently spinning placeholder.
    """
    registry = load_registry(get_settings().content_dir)
    referenced: dict[str, set[str]] = {}
    for locale, lessons in registry.markdown.items():
        for lesson_id, body in lessons.items():
            for figure_id in _FIGURE_REF.findall(body):
                assert figure_id in registry.figures, (
                    f"{locale}/{lesson_id} embeds unknown figure {figure_id!r}"
                )
                referenced.setdefault(figure_id, set()).add(locale)
    orphans = sorted(set(registry.figures) - set(referenced))
    assert not orphans, f"figure specs no lesson embeds: {orphans}"
    # ...and in BOTH languages: a figure the ES lesson shows and the EN one does not is a lesson that
    # silently teaches less in one language.
    one_sided = {fid: sorted(locs) for fid, locs in referenced.items() if len(locs) < 2}
    assert not one_sided, f"figures embedded in only one language: {one_sided}"


def test_figure_only_injectors_are_never_used_by_an_exercise() -> None:
    """No exercise config selects a figure-only injector: those resolve their scenario on screen."""
    registry = load_registry(get_settings().content_dir)
    for _, _, exercise in registry.manifest.iter_exercises():
        config = registry.get_exercise_config(exercise.id)
        injector = getattr(config, "injector", None)
        assert injector not in _FIGURE_ONLY_INJECTORS, (
            f"{exercise.id} uses the figure-only injector {injector!r}, which shows its own answer"
        )


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
