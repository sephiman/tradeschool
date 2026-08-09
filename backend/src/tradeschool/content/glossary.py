# SPDX-License-Identifier: AGPL-3.0-only
"""The glossary: `content/glossary.yaml` parsed, validated against the manifest, and sorted per locale."""

from __future__ import annotations

import unicodedata
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from tradeschool.content.schema import LocalizedText


def _plain(text: LocalizedText, where: str) -> None:
    """Definitions are plain text, not markdown.

    The PDF prints them verbatim into a pdfmake text node and the app renders them as a string, so
    `*emphasis*` would reach the reader as literal asterisks on both surfaces.
    """
    for locale in ("en", "es"):
        value = text.get(locale)
        for markup in ("*", "_`", "`"):
            if markup in value:
                raise ValueError(f"{where} ({locale}): definitions are plain text, found {markup!r}")


class GlossarySense(BaseModel):
    """One meaning of a term the course uses in more than one sense."""

    model_config = ConfigDict(extra="forbid")
    origin: str
    definition: LocalizedText

    @model_validator(mode="after")
    def _plain_text(self) -> Self:
        _plain(self.definition, f"sense of {self.origin}")
        return self


class MatchVariants(BaseModel):
    """The surface forms the annotator looks for, where the derived default is wrong for a locale."""

    model_config = ConfigDict(extra="forbid")
    en: list[str] | None = None
    es: list[str] | None = None

    def get(self, locale: str) -> list[str] | None:
        return self.es if locale == "es" else self.en

    @model_validator(mode="after")
    def _usable(self) -> Self:
        for locale in ("en", "es"):
            variants = self.get(locale)
            if variants is None:
                continue
            if not variants:
                raise ValueError(f"match ({locale}): an empty list means 'never matches', use link: false")
            for variant in variants:
                if variant != variant.strip() or not variant:
                    raise ValueError(f"match ({locale}): {variant!r} is blank or padded")
            if len(set(variants)) != len(variants):
                raise ValueError(f"match ({locale}): duplicate variant")
        return self


class LocaleFlags(BaseModel):
    """A per-locale switch: the two languages meet different homonyms, so they opt out separately."""

    model_config = ConfigDict(extra="forbid")
    en: bool = True
    es: bool = True

    def get(self, locale: str) -> bool:
        return self.es if locale == "es" else self.en


class LocaleLessons(BaseModel):
    """Per-locale lesson lists, for a word that is a false friend in one language only."""

    model_config = ConfigDict(extra="forbid")
    en: list[str] = Field(default_factory=list)
    es: list[str] = Field(default_factory=list)

    def get(self, locale: str) -> list[str]:
        return self.es if locale == "es" else self.en

    def all(self) -> list[str]:
        return [*self.en, *self.es]


class GlossaryTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    en: str
    es: str
    # Omitted only by a pure homonym, where there is no single teaching lesson and each sense
    # carries its own origin instead.
    origin: str | None = None
    definition: LocalizedText | None = None
    senses: list[GlossarySense] = Field(default_factory=list)
    alias_of: str | None = None
    # --- annotation: which occurrences in the prose become a link. See content/README.md.
    link: bool | LocaleFlags = True
    match: MatchVariants | None = None
    link_except: list[str] | LocaleLessons = Field(default_factory=list)

    def term(self, locale: str) -> str:
        return self.es if locale == "es" else self.en

    def origins(self) -> list[str]:
        """Every lesson this entry points back at — its own, or one per sense."""
        return [o for o in (self.origin, *(s.origin for s in self.senses)) if o is not None]

    def links(self, locale: str) -> bool:
        return self.link.get(locale) if isinstance(self.link, LocaleFlags) else self.link

    def excluded_lessons(self, locale: str) -> list[str]:
        """Lessons where a match is NOT this term — a false friend, not an occurrence to spend."""
        if isinstance(self.link_except, LocaleLessons):
            return self.link_except.get(locale)
        return self.link_except

    def all_excluded_lessons(self) -> list[str]:
        if isinstance(self.link_except, LocaleLessons):
            return self.link_except.all()
        return self.link_except

    @model_validator(mode="after")
    def _shape(self) -> Self:
        if self.alias_of is not None:
            if self.definition is not None or self.senses:
                raise ValueError(f"glossary {self.id!r}: an alias cannot carry its own definition")
        elif self.definition is None and not self.senses:
            raise ValueError(f"glossary {self.id!r}: needs a definition, senses, or alias_of")
        if self.origin is None and not self.senses:
            raise ValueError(f"glossary {self.id!r}: needs an origin unless it has senses")
        if self.definition is not None:
            _plain(self.definition, f"glossary {self.id!r}")
        off = [loc for loc in ("en", "es") if not self.links(loc)]
        for locale in off:
            if (self.match is not None and self.match.get(locale) is not None) or self.excluded_lessons(
                locale
            ):
                raise ValueError(f"glossary {self.id!r}: link is off for {locale}, so it needs no rules")
        excluded = self.all_excluded_lessons()
        if len(set(excluded)) != len(excluded):
            raise ValueError(f"glossary {self.id!r}: duplicate lesson in link_except")
        return self


class Glossary(BaseModel):
    model_config = ConfigDict(extra="forbid")
    terms: list[GlossaryTerm]

    @model_validator(mode="after")
    def _validate(self) -> Self:
        ids = [t.id for t in self.terms]
        duplicates = {i for i in ids if ids.count(i) > 1}
        if duplicates:
            raise ValueError(f"duplicate glossary id(s): {sorted(duplicates)}")
        known = set(ids)
        for term in self.terms:
            if term.alias_of is not None:
                if term.alias_of not in known:
                    raise ValueError(f"glossary {term.id!r}: alias_of unknown id {term.alias_of!r}")
                target = next(t for t in self.terms if t.id == term.alias_of)
                # One hop only: an alias of an alias has no definition to reach.
                if target.alias_of is not None:
                    raise ValueError(f"glossary {term.id!r}: alias_of points at another alias")
        return self

    def sorted_terms(self, locale: str) -> list[GlossaryTerm]:
        """Alphabetical in `locale`, accent-insensitive — the two locales sort differently by design."""
        return sorted(self.terms, key=lambda t: _sort_key(t.term(locale)))


def _sort_key(value: str) -> str:
    """Fold case and accents so `emisión` sorts with `e`, not after `z`."""
    lowered = value.casefold()
    stripped = unicodedata.normalize("NFD", lowered)
    return "".join(c for c in stripped if unicodedata.category(c) != "Mn")


def load_glossary(content_dir: Path, lesson_ids: set[str], taken_ids: set[str]) -> Glossary:
    """Parse the glossary and check it against the manifest it refers into.

    `taken_ids` is every other stable id in the repo: glossary ids share that one namespace, so a
    collision here would be as permanent a mistake as a duplicate lesson id.
    """
    path = content_dir / "glossary.yaml"
    if not path.exists():
        return Glossary(terms=[])
    with path.open(encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    glossary = Glossary.model_validate(raw)

    for term in glossary.terms:
        if term.id in taken_ids:
            raise ValueError(f"glossary id {term.id!r} collides with an existing content id")
        for origin in term.origins():
            if origin not in lesson_ids:
                raise ValueError(f"glossary {term.id!r}: unknown origin lesson {origin!r}")
        for excluded in term.all_excluded_lessons():
            if excluded not in lesson_ids:
                raise ValueError(f"glossary {term.id!r}: unknown lesson {excluded!r} in link_except")
    return glossary
