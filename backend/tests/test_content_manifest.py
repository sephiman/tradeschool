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
    # 29 modules across 6 blocks.
    assert len(registry.manifest.blocks) == 6
    assert len(registry.manifest.iter_modules()) == 29
    # Every authored lesson exists in both languages (load_registry enforces it).
    for locale in ("en", "es"):
        assert "m06-l1" in registry.markdown[locale]


def test_all_phase1_exercises_are_playable() -> None:
    # Every exercise declared in the manifest must have a valid, loaded generator config.
    registry = load_registry(get_settings().content_dir)
    for _, _, exercise in registry.manifest.iter_exercises():
        assert registry.get_exercise_config(exercise.id) is not None, f"{exercise.id} not playable"


def test_every_figure_reference_resolves_and_no_spec_is_orphaned() -> None:
    """A `::figure{id=…}` directive is a plain string in prose, so a typo or a renamed spec produces a
    lesson with a permanently spinning placeholder — nothing server-side objects. Both directions are
    checked: every reference must resolve to a loaded spec, and every spec must be referenced by some
    lesson, so a figure that was built and never embedded cannot sit unused in the tree."""
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
    """The four figure-only injectors resolve their scenario on screen — the ladder continues, the trade
    reaches its target, the limit never fills. That is the point of a figure and the opposite of what an
    exercise may show, so no exercise config is allowed to select one."""
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
