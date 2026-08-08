# SPDX-License-Identifier: AGPL-3.0-only
"""The glossary's promises: it refers into real lessons, it never coins, and it sorts per locale."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from tradeschool.config import get_settings
from tradeschool.content.glossary import Glossary, GlossaryTerm
from tradeschool.content.registry import load_registry
from tradeschool.content.schema import LOCALES, LocalizedText


def _def(s: str = "d") -> LocalizedText:
    return LocalizedText(en=s, es=s)


# --- the real glossary ---


def test_real_glossary_loads_and_every_origin_is_a_real_lesson() -> None:
    registry = load_registry(get_settings().content_dir)
    lesson_ids = {lesson.id for _, lesson in registry.manifest.iter_lessons()}
    assert registry.glossary.terms, "glossary is empty"
    for term in registry.glossary.terms:
        origins = [o for o in (term.origin, *(s.origin for s in term.senses)) if o]
        assert origins, f"{term.id} has no origin at all"
        for origin in origins:
            assert origin in lesson_ids, f"{term.id} -> {origin}"


def test_glossary_ids_do_not_collide_with_any_other_stable_id() -> None:
    registry = load_registry(get_settings().content_dir)
    manifest = registry.manifest
    taken = (
        {manifest.course.id}
        | {b.id for b in manifest.blocks}
        | manifest.module_ids()
        | {lesson.id for _, lesson in manifest.iter_lessons()}
        | {ex.id for _, _, ex in manifest.iter_exercises()}
        | set(registry.figures)
    )
    for term in registry.glossary.terms:
        assert term.id not in taken, f"glossary id {term.id} collides"


@pytest.mark.parametrize("locale", LOCALES)
def test_every_entry_renders_in_both_locales(locale: str) -> None:
    registry = load_registry(get_settings().content_dir)
    entries = registry.glossary_entries(locale)
    assert len(entries) == len(registry.glossary.terms)
    for entry in entries:
        assert entry["term"], f"{entry['id']} has no term in {locale}"
        # An alias defers its definition to the canonical entry; everything else states one.
        if "aliasOf" in entry:
            assert "definition" not in entry and "senses" not in entry
            assert entry["aliasOf"]["term"]
        else:
            assert entry.get("definition") or entry.get("senses")


@pytest.mark.parametrize("locale", LOCALES)
def test_entries_are_alphabetical_in_that_locale(locale: str) -> None:
    from tradeschool.content.glossary import _sort_key

    registry = load_registry(get_settings().content_dir)
    terms = [str(e["term"]) for e in registry.glossary_entries(locale)]
    assert terms == sorted(terms, key=_sort_key)


def test_the_two_locales_do_not_share_one_order() -> None:
    """ES sorts `apalancamiento` near the top where EN sorts `leverage` mid-list. That is the design."""
    registry = load_registry(get_settings().content_dir)
    es = [e["id"] for e in registry.glossary_entries("es")]
    en = [e["id"] for e in registry.glossary_entries("en")]
    assert set(es) == set(en)
    assert es != en


def test_accented_terms_sort_with_their_base_letter() -> None:
    from tradeschool.content.glossary import _sort_key

    # `emisión` must land under E, not after Z.
    assert _sort_key("emisión") < _sort_key("envolvente") < _sort_key("esperanza")


def test_export_carries_the_glossary_in_both_shapes() -> None:
    registry = load_registry(get_settings().content_dir)
    single = registry.course_export("es")
    assert [e["term"] for e in single["glossary"]] == [e["term"] for e in registry.glossary_entries("es")]
    bilingual = registry.course_export_bilingual()
    assert set(bilingual["glossary"]) == set(LOCALES)
    assert bilingual["glossary"]["en"] != bilingual["glossary"]["es"]


# --- the structural rules, on synthetic input ---


def test_an_alias_may_not_carry_its_own_definition() -> None:
    with pytest.raises(ValidationError, match="alias cannot carry its own definition"):
        GlossaryTerm(id="g-a", en="a", es="a", origin="m01-l1", alias_of="g-b", definition=_def())


def test_an_entry_needs_a_definition_senses_or_alias() -> None:
    with pytest.raises(ValidationError, match="needs a definition, senses, or alias_of"):
        GlossaryTerm(id="g-a", en="a", es="a", origin="m01-l1")


def test_an_entry_without_senses_needs_an_origin() -> None:
    with pytest.raises(ValidationError, match="needs an origin unless it has senses"):
        GlossaryTerm(id="g-a", en="a", es="a", definition=_def())


def test_alias_of_must_point_at_a_known_entry() -> None:
    with pytest.raises(ValidationError, match="alias_of unknown id"):
        Glossary(terms=[GlossaryTerm(id="g-a", en="a", es="a", origin="m01-l1", alias_of="g-missing")])


def test_an_alias_may_not_point_at_another_alias() -> None:
    """One hop only — a chained alias has no definition to reach."""
    with pytest.raises(ValidationError, match="points at another alias"):
        Glossary(
            terms=[
                GlossaryTerm(id="g-a", en="a", es="a", origin="m01-l1", definition=_def()),
                GlossaryTerm(id="g-b", en="b", es="b", origin="m01-l1", alias_of="g-a"),
                GlossaryTerm(id="g-c", en="c", es="c", origin="m01-l1", alias_of="g-b"),
            ]
        )


def test_the_glossary_never_coins_guard_fires_on_a_term_absent_from_the_prose() -> None:
    from tradeschool.content.registry import ContentError, _check_glossary_never_coins

    markdown = {"en": {"m01-l1": "a lesson about candles"}, "es": {"m01-l1": "una lección de velas"}}
    ok = Glossary(terms=[GlossaryTerm(id="g-c", en="candle", es="vela", origin="m01-l1", definition=_def())])
    _check_glossary_never_coins(ok, markdown)  # present in both locales

    coined = Glossary(
        terms=[GlossaryTerm(id="g-x", en="candle", es="patrón inventado", origin="m01-l1", definition=_def())]
    )
    with pytest.raises(ContentError, match="never coins"):
        _check_glossary_never_coins(coined, markdown)


def test_never_coins_matches_across_the_prose_hard_wrap() -> None:
    """Lesson prose wraps at ~100 cols, so a multi-word term is routinely split over two lines."""
    from tradeschool.content.registry import _check_glossary_never_coins

    markdown = {
        "en": {"m01-l1": "the resting\norder book is thin"},
        "es": {"m01-l1": "el libro de\nórdenes está fino"},
    }
    wrapped = Glossary(
        terms=[
            GlossaryTerm(
                id="g-ob", en="order book", es="libro de órdenes", origin="m01-l1", definition=_def()
            )
        ]
    )
    _check_glossary_never_coins(wrapped, markdown)


def test_definitions_must_be_plain_text_not_markdown() -> None:
    """Both surfaces print a definition verbatim, so `*emphasis*` would reach the reader as asterisks."""
    with pytest.raises(ValidationError, match="plain text"):
        GlossaryTerm(
            id="g-a",
            en="a",
            es="a",
            origin="m01-l1",
            definition=LocalizedText(en="its *own*", es="lo *suyo*"),
        )


def test_the_real_glossary_carries_no_markup() -> None:
    registry = load_registry(get_settings().content_dir)
    for term in registry.glossary.terms:
        for locale in LOCALES:
            texts = [
                *([term.definition.get(locale)] if term.definition else []),
                *(s.definition.get(locale) for s in term.senses),
            ]
            for text in texts:
                assert "*" not in text and "`" not in text, f"{term.id} ({locale})"


def test_duplicate_glossary_ids_are_rejected() -> None:
    with pytest.raises(ValidationError, match="duplicate glossary id"):
        Glossary(
            terms=[
                GlossaryTerm(id="g-a", en="a", es="a", origin="m01-l1", definition=_def()),
                GlossaryTerm(id="g-a", en="b", es="b", origin="m01-l1", definition=_def()),
            ]
        )
