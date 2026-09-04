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
    ManifestLesson,
    ManifestModule,
)

_FIGURE_REF = re.compile(r"::figure\{id=([^}\s]+)\}")
# Injectors that exist only to draw lesson figures. A figure SHOWS the resolution; an exercise must cut
# before it, so an exercise built on one of these would hand over its own answer.
_FIGURE_ONLY_INJECTORS = {"market_structure", "liquidity_sweep", "stop_limit_gap", "trade_anatomy"}


def _t(s: str) -> LocalizedText:
    return LocalizedText(en=s, es=s)


def _course() -> ManifestCourse:
    return ManifestCourse(id="c1", title=_t("Course"), subtitle=_t("Course"), description=_t("desc"))


def test_real_manifest_loads_and_lessons_have_both_languages() -> None:
    registry = load_registry(get_settings().content_dir)
    # The single course today owns all existing content under a stable id.
    assert registry.manifest.course.id == "crypto-futures"
    assert registry.manifest.course.title.en and registry.manifest.course.description.es
    # 35 modules across 7 blocks. (The old "block G is the trailing single-module block" guard was
    # RETIRED 2026-08-10 when block-g merged into block-f — the SMC dialect is now f's closing
    # module, not a block of its own; the numbering-continuity invariant below replaces it. The
    # letter came back 2026-08-23 for the epilogue, whose single-module shape is pinned below.)
    assert len(registry.manifest.blocks) == 7
    assert len(registry.manifest.iter_modules()) == 35
    # Numbering continuity — a PERMANENT invariant for any future restructure, not just today's:
    # (a) module display numbers run m01..m34 strictly consecutive, ascending across every block
    #     boundary, with no gaps; permanent identity (seeds, progress) lives on `key`, never here.
    module_ids = [m.id for _, m in registry.manifest.iter_modules()]
    assert module_ids == [f"m{i:02d}" for i in range(1, len(module_ids) + 1)]
    # (b) block identifiers are consecutive letters with no hole where a removed block used to be.
    assert [b.id for b in registry.manifest.blocks] == [
        f"block-{chr(ord('a') + i)}" for i in range(len(registry.manifest.blocks))
    ]
    block_c = next(b for b in registry.manifest.blocks if b.id == "block-c")
    assert [m.id for m in block_c.modules][-3:] == ["m14", "m15", "m16"]
    # The two modules the renumbering genuinely MOVED (not just relabeled), pinned with their keys:
    # m21 (key m34) closed block D so its m21-l2 -> m20 tokenomics lean reads backward, and m28
    # (key m33) became block E's capstone, after the m26/m27 material it treats as known.
    block_d = next(b for b in registry.manifest.blocks if b.id == "block-d")
    block_e = next(b for b in registry.manifest.blocks if b.id == "block-e")
    assert [m.id for m in block_d.modules] == ["m17", "m18", "m19", "m20", "m21"]
    assert [m.id for m in block_e.modules] == ["m22", "m23", "m24", "m25", "m26", "m27", "m28"]
    assert next(m for m in block_d.modules if m.id == "m21").key == "m34"
    assert next(m for m in block_e.modules if m.id == "m28").key == "m33"
    # The epilogue: one module on purpose (an epilogue is an island — see the manifest comment), a
    # semantic key, and the course's only lesson with no exercises.
    block_g = next(b for b in registry.manifest.blocks if b.id == "block-g")
    assert [m.id for m in block_g.modules] == ["m35"]
    assert block_g.modules[0].key == "epilogue"
    assert [lesson.exercises for lesson in block_g.modules[0].lessons] == [[]]
    assert [
        lesson.id for _, lesson in registry.manifest.iter_lessons() if not lesson.exercises
    ] == ["m35-l1"]
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


# --- lesson summaries -----------------------------------------------------------------------------


def test_every_lesson_carries_a_summary_in_both_locales() -> None:
    """A summary is required content, not an optional decoration — the app has a slot for it."""
    registry = load_registry(get_settings().content_dir)
    for _module, lesson in registry.manifest.iter_lessons():
        for locale in ("en", "es"):
            summary = lesson.summary.get(locale)
            assert summary.strip(), f"{lesson.id} ({locale}) has an empty summary"
            # Two or three sentences. The floor catches a placeholder; the ceiling catches a summary
            # that has quietly become the lesson again. A terminator is only a terminator when
            # whitespace or the end follows it, which is what keeps `9.5%` and `0.618` out of the count.
            assert 120 <= len(summary) <= 800, f"{lesson.id} ({locale}) is {len(summary)} chars"
            sentences = len(re.findall(r"[.!?](?=\s|$)", summary))
            assert 2 <= sentences <= 4, f"{lesson.id} ({locale}) reads as {sentences} sentences"


def test_a_summary_never_coins_a_term_its_own_lesson_does_not_use() -> None:
    """The glossary's promise, per lesson: a summary may not introduce vocabulary the prose lacks.

    Load-bearing because a summary is the first thing a reader sees about a lesson — in the app it is
    what a tapped lesson reference shows — so a term appearing only there promises a definition the
    lesson never delivers.
    """
    from tradeschool.content.registry import _check_summaries_never_coin

    registry = load_registry(get_settings().content_dir)
    # The real course passes; this is the assertion the content itself has to keep meeting.
    _check_summaries_never_coin(registry.manifest, registry.glossary, registry.markdown)


def test_the_summary_guard_fires_on_a_term_the_lesson_never_uses() -> None:
    """Red on purpose: the guard is worthless if it says yes to everything."""
    from tradeschool.content.glossary import Glossary, GlossaryTerm
    from tradeschool.content.registry import ContentError, _check_summaries_never_coin

    def _lesson(summary: str) -> ManifestLesson:
        return ManifestLesson(id="m01-l1", title=_t("t"), summary=LocalizedText(en=summary, es=summary))

    def _manifest(lesson: ManifestLesson) -> Manifest:
        return Manifest(
            course=ManifestCourse(id="c", title=_t("t"), subtitle=_t("s"), description=_t("d")),
            blocks=[
                ManifestBlock(
                    id="block-a",
                    title=_t("b"),
                    modules=[ManifestModule(id="m01", title=_t("m"), summary=_t("s"), lessons=[lesson])],
                )
            ],
        )

    glossary = Glossary(
        terms=[
            GlossaryTerm(
                id="g-funding",
                en="funding",
                es="funding",
                origin="m01-l1",
                definition=LocalizedText(en="d", es="d"),
            )
        ]
    )
    markdown = {"en": {"m01-l1": "a lesson about candles"}, "es": {"m01-l1": "a lesson about candles"}}

    clean = _lesson("This lesson is about candles and what a candle hides from you.")
    _check_summaries_never_coin(_manifest(clean), glossary, markdown)

    coined = _lesson("This lesson is about funding, which the prose below never mentions at all.")
    with pytest.raises(ContentError, match="never coins either"):
        _check_summaries_never_coin(_manifest(coined), glossary, markdown)


def test_the_summary_guard_does_not_fire_on_a_substring_or_an_inflection() -> None:
    """The two asymmetries the matcher is built on, each shown to matter.

    A term found as a SUBSTRING of a longer word in the summary would fail a summary that is fine;
    an inflection in the PROSE answering for its stem is the laxness the glossary rule already has.
    """
    from tradeschool.content.glossary import Glossary, GlossaryTerm
    from tradeschool.content.registry import _check_summaries_never_coin

    def _lesson(summary: str) -> ManifestLesson:
        return ManifestLesson(id="m01-l1", title=_t("t"), summary=LocalizedText(en=summary, es=summary))

    def _manifest(lesson: ManifestLesson) -> Manifest:
        return Manifest(
            course=ManifestCourse(id="c", title=_t("t"), subtitle=_t("s"), description=_t("d")),
            blocks=[
                ManifestBlock(
                    id="block-a",
                    title=_t("b"),
                    modules=[ManifestModule(id="m01", title=_t("m"), summary=_t("s"), lessons=[lesson])],
                )
            ],
        )

    def _glossary(term: str) -> Glossary:
        return Glossary(
            terms=[
                GlossaryTerm(
                    id="g-x", en=term, es=term, origin="m01-l1", definition=LocalizedText(en="d", es="d")
                )
            ]
        )

    # "range" inside "arrange" is not a use of the term.
    substring = {"en": {"m01-l1": "nothing here"}, "es": {"m01-l1": "nothing here"}}
    _check_summaries_never_coin(
        _manifest(_lesson("You arrange the orders before you ever open a position at all.")),
        _glossary("range"),
        substring,
    )

    # "liquidations" in the prose answers for the term "liquidation" in the summary.
    inflected = {"en": {"m01-l1": "cascading liquidations"}, "es": {"m01-l1": "cascading liquidations"}}
    _check_summaries_never_coin(
        _manifest(_lesson("A liquidation is a forced close, and it is the whole of this lesson.")),
        _glossary("liquidation"),
        inflected,
    )
