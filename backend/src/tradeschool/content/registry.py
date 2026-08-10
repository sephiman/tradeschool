# SPDX-License-Identifier: AGPL-3.0-only
"""In-memory course registry: the manifest plus loaded lesson markdown, with localized query
helpers used by the content endpoints. Built once at startup from `content/`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from pydantic import BaseModel, ValidationError

from tradeschool.content.glossary import Glossary, GlossaryTerm, load_glossary
from tradeschool.content.reading import estimate_seconds
from tradeschool.content.schema import (
    LOCALES,
    LocalizedText,
    Manifest,
    ManifestBlock,
    ManifestExercise,
    ManifestLesson,
    ManifestModule,
    parse_manifest,
)
from tradeschool.exercises.figures import FigureSpec, load_figures
from tradeschool.exercises.registry import get_generator, has_generator
from tradeschool.exercises.types import ExerciseType

logger = logging.getLogger("tradeschool.content")


class ContentError(RuntimeError):
    """Raised when the manifest and content trees are inconsistent."""


_EXERCISE_DIRECTIVE = re.compile(r"^::exercise\{[^}]*\}[ \t]*$", re.MULTILINE)


def _theory_only(markdown: str) -> str:
    """Strip the ``::exercise{...}`` directives, leaving only prose, and collapse the blank lines."""
    stripped = _EXERCISE_DIRECTIVE.sub("", markdown)
    return re.sub(r"\n{3,}", "\n\n", stripped).strip()


@dataclass(frozen=True)
class LessonLocation:
    block: ManifestBlock
    module: ManifestModule
    lesson: ManifestLesson


@dataclass
class CourseRegistry:
    manifest: Manifest
    # markdown[locale][lesson_id] -> body
    markdown: dict[str, dict[str, str]]
    # exercise_id -> (type, parsed generator config). Absent = declared but not yet playable.
    exercise_configs: dict[str, tuple[ExerciseType, BaseModel]] = field(default_factory=dict)
    # figure_id -> spec (lesson figures embedded via ::figure{id=...}).
    figures: dict[str, FigureSpec] = field(default_factory=dict)
    # The glossary, loaded once; sorted per locale on the way out.
    glossary: Glossary = field(default_factory=lambda: Glossary(terms=[]))
    # reading_seconds[locale][lesson_id] -> estimated reading time. Derived from the markdown once
    # here, so every surface that shows time is summing the same per-lesson numbers.
    reading_seconds: dict[str, dict[str, int]] = field(default_factory=dict)
    _modules: dict[str, tuple[ManifestBlock, ManifestModule]] = field(default_factory=dict)
    _lessons: dict[str, LessonLocation] = field(default_factory=dict)
    _exercises: dict[str, tuple[ManifestBlock, ManifestModule]] = field(default_factory=dict)
    # exercise_id -> lesson_id. Separate from _exercises because a module may hold two lessons,
    # so the module is not enough to route back to the page an exercise actually lives on.
    _exercise_lessons: dict[str, str] = field(default_factory=dict)
    # display id <-> permanent key, both directions, per entity level. The DB, seeds and glossary
    # origins live in key space; every API surface speaks display ids — these maps are the boundary.
    _module_keys: dict[str, str] = field(default_factory=dict)
    _module_ids: dict[str, str] = field(default_factory=dict)
    _lesson_keys: dict[str, str] = field(default_factory=dict)
    _lesson_ids: dict[str, str] = field(default_factory=dict)
    _exercise_keys: dict[str, str] = field(default_factory=dict)
    _exercise_ids: dict[str, str] = field(default_factory=dict)

    def get_exercise_config(self, exercise_id: str) -> tuple[ExerciseType, BaseModel] | None:
        return self.exercise_configs.get(exercise_id)

    def __post_init__(self) -> None:
        # Reading time is computed here — at load, once per (locale, lesson) — and never per request:
        # it is a pure function of the markdown, and the markdown only changes on restart.
        for locale, lessons in self.markdown.items():
            self.reading_seconds[locale] = {
                lesson_id: estimate_seconds(body) for lesson_id, body in lessons.items()
            }
        for block, module in self.manifest.iter_modules():
            self._modules[module.id] = (block, module)
            self._module_keys[module.id] = module.key
            self._module_ids[module.key] = module.id
            for lesson in module.lessons:
                self._lessons[lesson.id] = LessonLocation(block, module, lesson)
                self._lesson_keys[lesson.id] = lesson.key
                self._lesson_ids[lesson.key] = lesson.id
                for exercise in lesson.exercises:
                    self._exercises[exercise.id] = (block, module)
                    self._exercise_lessons[exercise.id] = lesson.id
                    self._exercise_keys[exercise.id] = exercise.key
                    self._exercise_ids[exercise.key] = exercise.id

    # --- id <-> key boundary ---
    def module_key(self, module_id: str) -> str:
        return self._module_keys[module_id]

    def lesson_key(self, lesson_id: str) -> str:
        return self._lesson_keys[lesson_id]

    def exercise_key(self, exercise_id: str) -> str:
        return self._exercise_keys[exercise_id]

    def module_id_for_key(self, key: str) -> str | None:
        """None for a key the manifest no longer carries (deactivated content, historical rows)."""
        return self._module_ids.get(key)

    def lesson_id_for_key(self, key: str) -> str | None:
        return self._lesson_ids.get(key)

    def exercise_id_for_key(self, key: str) -> str | None:
        return self._exercise_ids.get(key)

    # --- lookups ---
    def module_lesson_ids(self, module_id: str) -> list[str]:
        _, module = self._modules[module_id]
        return [lesson.id for lesson in module.lessons]

    def exercise_location(self, exercise_id: str) -> tuple[str, str] | None:
        """(block_id, module_id) for an exercise, or None if unknown."""
        found = self._exercises.get(exercise_id)
        return (found[0].id, found[1].id) if found else None

    def exercise_lesson_id(self, exercise_id: str) -> str | None:
        """The lesson an exercise is embedded in — what a link back to it has to address."""
        return self._exercise_lessons.get(exercise_id)

    def module_block(self, module_id: str) -> str | None:
        found = self._modules.get(module_id)
        return found[0].id if found else None

    def block_title(self, block_id: str, locale: str) -> str | None:
        for block in self.manifest.blocks:
            if block.id == block_id:
                return block.title.get(locale)
        return None

    def unmet_prereqs(self, module_id: str, completed_lesson_ids: set[str]) -> list[str]:
        """Assumed modules the learner has not touched (no completed lesson). Advisory only."""
        _, module = self._modules[module_id]
        unmet: list[str] = []
        for dep in module.assumes:
            dep_lessons = set(self.module_lesson_ids(dep))
            if not (dep_lessons & completed_lesson_ids):
                unmet.append(dep)
        return unmet

    def lesson_reading_seconds(self, lesson_id: str, locale: str) -> int:
        """Reading time for one lesson. The ONE number every surface sums; never re-estimated."""
        return self.reading_seconds.get(locale, {}).get(lesson_id, 0)

    def module_title(self, module_id: str, locale: str) -> str | None:
        found = self._modules.get(module_id)
        return found[1].title.get(locale) if found else None

    # --- serialization for the API ---
    def _exercise_dict(self, ex: ManifestExercise) -> dict[str, str]:
        return {"id": ex.id, "type": ex.type.value}

    def module_exercise_ids(self, module_id: str) -> list[str]:
        _, module = self._modules[module_id]
        return [ex.id for lesson in module.lessons for ex in lesson.exercises]

    def playable_module_exercises(self, module_id: str) -> list[str]:
        """Exercise ids in this module with a loaded, playable generator config — the exam-samplable set."""
        return [eid for eid in self.module_exercise_ids(module_id) if eid in self.exercise_configs]

    def course_meta(self, locale: str) -> dict[str, str]:
        """Root course identity for the course-page header (localized)."""
        course = self.manifest.course
        return {
            "id": course.id,
            "title": course.title.get(locale),
            "description": course.description.get(locale),
        }

    def course_tree(
        self,
        locale: str,
        completed_lesson_ids: set[str],
        passed_exercise_ids: set[str] | None = None,
    ) -> list[dict[str, object]]:
        passed = passed_exercise_ids or set()
        blocks: list[dict[str, object]] = []
        for b_index, block in enumerate(self.manifest.blocks, start=1):
            modules: list[dict[str, object]] = []
            for m_index, module in enumerate(block.modules, start=1):
                lessons = [
                    {
                        "id": lesson.id,
                        "order": l_index,
                        "title": lesson.title.get(locale),
                        "completed": lesson.id in completed_lesson_ids,
                        "readingSeconds": self.lesson_reading_seconds(lesson.id, locale),
                        "exercises": [self._exercise_dict(ex) for ex in lesson.exercises],
                    }
                    for l_index, lesson in enumerate(module.lessons, start=1)
                ]
                total = len(lessons)
                done = sum(1 for lesson in lessons if lesson["completed"])
                exercise_ids = self.module_exercise_ids(module.id)
                modules.append(
                    {
                        "id": module.id,
                        "order": m_index,
                        "title": module.title.get(locale),
                        "summary": module.summary.get(locale),
                        "assumes": module.assumes,
                        "unmetPrereqs": self.unmet_prereqs(module.id, completed_lesson_ids),
                        "hasContent": total > 0,
                        "lessonsTotal": total,
                        "lessonsCompleted": done,
                        # Reading (completion) and mastery (exercises passed) are separate signals.
                        "exercisesTotal": len(exercise_ids),
                        "exercisesPassed": sum(1 for eid in exercise_ids if eid in passed),
                        "lessons": lessons,
                    }
                )
            blocks.append(
                {"id": block.id, "order": b_index, "title": block.title.get(locale), "modules": modules}
            )
        return blocks

    def _export_blocks(
        self,
        localized: Callable[[LocalizedText], object],
        prose: Callable[[str], object],
    ) -> list[dict[str, object]]:
        """The export tree, with how to render a localized field left to the caller.

        One walk serves both the single-locale and bilingual exports, so they cannot carry different
        modules.
        """
        return [
            {
                "id": block.id,
                "title": localized(block.title),
                "modules": [
                    {
                        "id": module.id,
                        "title": localized(module.title),
                        "summary": localized(module.summary),
                        "lessons": [
                            {
                                "id": lesson.id,
                                "title": localized(lesson.title),
                                "markdown": prose(lesson.id),
                            }
                            for lesson in module.lessons
                        ],
                    }
                    for module in block.modules
                ],
            }
            for block in self.manifest.blocks
        ]

    def course_export(self, locale: str) -> dict[str, object]:
        """The whole course as structured theory in ONE language, prose only."""
        return {
            "locale": locale,
            "blocks": self._export_blocks(
                lambda text: text.get(locale),
                lambda lesson_id: _theory_only(self.markdown[locale][lesson_id]),
            ),
            "glossary": self.glossary_entries(locale),
        }

    def course_export_bilingual(self) -> dict[str, object]:
        """The same document with BOTH languages, every localized field as `{"en": …, "es": …}`.

        Discriminated by the key: this carries `locales`, the single-locale document carries `locale`.
        """
        return {
            "locales": list(LOCALES),
            "blocks": self._export_blocks(
                lambda text: {loc: text.get(loc) for loc in LOCALES},
                lambda lesson_id: {
                    loc: _theory_only(self.markdown[loc][lesson_id]) for loc in LOCALES
                },
            ),
            "glossary": {loc: self.glossary_entries(loc) for loc in LOCALES},
        }

    # --- glossary ---
    def _lesson_title(self, lesson_id: str | None, locale: str) -> str | None:
        loc = self._lessons.get(lesson_id) if lesson_id else None
        return loc.lesson.title.get(locale) if loc else None

    def _glossary_entry(self, term: GlossaryTerm, locale: str) -> dict[str, object]:
        # glossary.yaml stores lesson KEYS (permanent); every surface gets the display id.
        origin_id = self.lesson_id_for_key(term.origin) if term.origin else None
        entry: dict[str, object] = {
            "id": term.id,
            "term": term.term(locale),
            "origin": origin_id,
            "originTitle": self._lesson_title(origin_id, locale),
        }
        # The annotator's inputs, carried on the entry so both surfaces read one description of what
        # may be linked. Absent keys mean "the default", which the annotator derives.
        if not term.links(locale):
            entry["link"] = False
        if term.match is not None and term.match.get(locale) is not None:
            entry["match"] = term.match.get(locale)
        if term.excluded_lessons(locale):
            entry["linkExcept"] = [
                self.lesson_id_for_key(key) for key in term.excluded_lessons(locale)
            ]
        if term.alias_of is not None:
            target = next(t for t in self.glossary.terms if t.id == term.alias_of)
            entry["aliasOf"] = {"id": target.id, "term": target.term(locale)}
        if term.definition is not None:
            entry["definition"] = term.definition.get(locale)
        if term.senses:
            entry["senses"] = [
                {
                    "origin": self.lesson_id_for_key(sense.origin),
                    "originTitle": self._lesson_title(self.lesson_id_for_key(sense.origin), locale),
                    "definition": sense.definition.get(locale),
                }
                for sense in term.senses
            ]
        return entry

    def glossary_entries(self, locale: str) -> list[dict[str, object]]:
        """Every entry, alphabetical in `locale`. Aliases render in place, pointing at the canonical."""
        return [self._glossary_entry(t, locale) for t in self.glossary.sorted_terms(locale)]

    def lesson_detail(
        self, lesson_id: str, locale: str, completed_lesson_ids: set[str]
    ) -> dict[str, object] | None:
        loc = self._lessons.get(lesson_id)
        if loc is None:
            return None
        return {
            "id": loc.lesson.id,
            "title": loc.lesson.title.get(locale),
            "moduleId": loc.module.id,
            "moduleTitle": loc.module.title.get(locale),
            "blockId": loc.block.id,
            "markdown": self.markdown[locale][lesson_id],
            "completed": lesson_id in completed_lesson_ids,
            "readingSeconds": self.lesson_reading_seconds(lesson_id, locale),
            "exercises": [self._exercise_dict(ex) for ex in loc.lesson.exercises],
        }

    def module_detail(
        self, module_id: str, locale: str, completed_lesson_ids: set[str]
    ) -> dict[str, object] | None:
        found = self._modules.get(module_id)
        if found is None:
            return None
        _, module = found
        return {
            "id": module.id,
            "title": module.title.get(locale),
            "summary": module.summary.get(locale),
            "assumes": [
                {"id": dep, "title": self.module_title(dep, locale)} for dep in module.assumes
            ],
            "unmetPrereqs": [
                {"id": dep, "title": self.module_title(dep, locale)}
                for dep in self.unmet_prereqs(module_id, completed_lesson_ids)
            ],
            "lessons": [
                {
                    "id": lesson.id,
                    "order": index,
                    "title": lesson.title.get(locale),
                    "completed": lesson.id in completed_lesson_ids,
                    "readingSeconds": self.lesson_reading_seconds(lesson.id, locale),
                }
                for index, lesson in enumerate(module.lessons, start=1)
            ],
        }


def _lesson_path(content_dir: Path, locale: str, lesson_id: str) -> Path:
    return content_dir / locale / "lessons" / f"{lesson_id}.md"


def _load_exercise_configs(
    content_dir: Path, manifest: Manifest
) -> dict[str, tuple[ExerciseType, BaseModel]]:
    configs: dict[str, tuple[ExerciseType, BaseModel]] = {}
    for _, _, exercise in manifest.iter_exercises():
        path = content_dir / "exercises" / f"{exercise.id}.yaml"
        if not path.exists():
            # Declared but not yet authored — the exercise simply isn't playable yet.
            logger.info("no config for exercise %s; not playable yet", exercise.id)
            continue
        if not has_generator(exercise.type):
            logger.info("no generator for %s (%s); skipping", exercise.id, exercise.type.value)
            continue
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if not isinstance(raw, dict):
            raise ContentError(f"exercise config {path} is not a mapping")
        declared = raw.get("type")
        if declared != exercise.type.value:
            raise ContentError(
                f"exercise {exercise.id!r}: manifest type {exercise.type.value!r} != config {declared!r}"
            )
        try:
            parsed = get_generator(exercise.type).parse_config(raw)
        except ValidationError as exc:
            raise ContentError(f"invalid config for exercise {exercise.id!r}: {exc}") from exc
        configs[exercise.id] = (exercise.type, parsed)
    return configs


def load_registry(content_dir: Path) -> CourseRegistry:
    manifest_path = content_dir / "course.yaml"
    if not manifest_path.exists():
        raise ContentError(f"manifest not found: {manifest_path}")
    manifest = parse_manifest(manifest_path)

    markdown: dict[str, dict[str, str]] = {locale: {} for locale in LOCALES}
    for _, lesson in manifest.iter_lessons():
        for locale in LOCALES:
            path = _lesson_path(content_dir, locale, lesson.id)
            if not path.exists():
                raise ContentError(f"missing {locale} lesson file for {lesson.id!r}: {path}")
            body = path.read_text(encoding="utf-8").strip()
            if not body:
                raise ContentError(f"empty {locale} lesson file for {lesson.id!r}: {path}")
            markdown[locale][lesson.id] = body

    exercise_configs = _load_exercise_configs(content_dir, manifest)
    figures = load_figures(content_dir)

    # Glossary origins/exclusions are lesson KEYS; glossary ids must be free of ids AND keys.
    lesson_keys = {lesson.key for _, lesson in manifest.iter_lessons()}
    taken_ids = (
        {manifest.course.id}
        | {b.id for b in manifest.blocks}
        | manifest.module_ids()
        | {m.key for _, m in manifest.iter_modules()}
        | {lesson.id for _, lesson in manifest.iter_lessons()}
        | lesson_keys
        | {ex.id for _, _, ex in manifest.iter_exercises()}
        | {ex.key for _, _, ex in manifest.iter_exercises()}
        | set(figures)
        | {spec.key for spec in figures.values()}
    )
    glossary = load_glossary(content_dir, lesson_keys, taken_ids)
    _check_glossary_never_coins(glossary, markdown)

    return CourseRegistry(
        manifest=manifest,
        markdown=markdown,
        exercise_configs=exercise_configs,
        figures=figures,
        glossary=glossary,
    )


def _check_glossary_never_coins(glossary: Glossary, markdown: dict[str, dict[str, str]]) -> None:
    """Every term must actually appear in the prose of its own locale — the glossary never coins.

    Prose is hard-wrapped, so a multi-word term is routinely split across lines; match against
    whitespace-flattened text or every such term reads as absent.
    """
    flattened = {
        locale: " ".join(" ".join(body.split()) for body in lessons.values())
        for locale, lessons in markdown.items()
    }
    missing: list[str] = []
    for term in glossary.terms:
        for locale in LOCALES:
            needle = " ".join(term.term(locale).split()).casefold()
            # Parenthetical glosses in the term itself ("open interest (OI)") are display sugar;
            # match on the head, which is what the prose actually writes.
            needle = needle.split(" (")[0]
            if needle not in flattened[locale].casefold():
                missing.append(f"{term.id} ({locale}: {needle!r})")
    if missing:
        raise ContentError(
            "glossary terms that never appear in that locale's prose (the glossary never coins): "
            + ", ".join(missing)
        )
