# SPDX-License-Identifier: AGPL-3.0-only
"""Build `dist/bundle/` — the content the native Android app reads instead of calling this backend.

Phase W2. One command, and it has to be one command: the bundle is half Python and half TypeScript,
and a two-step export is a bundle whose halves can be from different content versions.

  * Python owns `content/`. The manifest, the 147 exercise configs as the engine parses them, the 34
    figure specs, the glossary in both locales, the 88 reading-time integers, the calculation
    error-phrase table and `figure-coupling.yaml` all come off the `CourseRegistry` this backend
    already builds at startup — the same loader, the same validation, no second reader.
  * TypeScript owns the mdast. The parser dialect, the ONE annotator that decides which words are
    glossary marks and lesson references, and the tap point between it and the hast hints are all in
    `frontend/src/lib/`. So this script writes an input file, drives `frontend/scripts/export-ast.mjs`
    with it, and never parses a line of markdown itself.

Two things it refuses to write a bundle without.

**The block inventory.** `BLOCK_INVENTORY` is the closed set of mdast node kinds the app can render.
An unknown node does not crash a renderer, it renders as nothing — so a lesson that acquires a fenced
code block, an image, a hard line break or an `####` heading would ship as a hole in the page with
nothing anywhere to notice. Every node of every lesson AST is checked against the inventory and the
export fails naming the lesson, the path to the node and the kind. This is the guard that keeps
future web content inside what the app can draw, and `tests/test_export_bundle.py` asserts it says no
to each way that could break, one test per kind.

**The text checks.** The AST half re-reads what it wrote and holds it against the web twice. A
multiset diff compares the words in it with the words `/api/courses/{course}/export` serves from the
same content, per locale, prose and glossary; a block diff compares each lesson, block for block and
in order, with the page `LessonMarkdown` actually paints. Both must come out empty. Between them they
catch the failure modes a bundle crossing a repository boundary actually has and none of which is
loud: a text node dropped while splitting it around a mark, a lost node, a re-encoded `→`, a stale
file from a partial export, a paragraph in the wrong place, a soft break that became a hard one.

Two checks and not one because the multiset alone cannot be asked about whitespace (it splits on it),
about order (it is a bag), or about a change to the parser itself (its reference comes off that same
parser). The block diff's reference is the rendered DOM, which shares no code with the bundle's path.

Usage (from `backend/`):
    uv run python scripts/export_bundle.py
    uv run python scripts/export_bundle.py --out ../dist/bundle --no-verify
    uv run python scripts/export_bundle.py --skip-ast     # Python half only (no node needed)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import time
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parent.parent
for _extra in (_BACKEND / "src",):
    if str(_extra) not in sys.path:
        sys.path.insert(0, str(_extra))

from pydantic import BaseModel  # noqa: E402

from tradeschool.content.registry import CourseRegistry, _theory_only, load_registry  # noqa: E402
from tradeschool.content.schema import LOCALES  # noqa: E402
from tradeschool.exercises.calculation import (  # noqa: E402
    MISTAKE_SENTENCES,
    MISTAKE_TRANSLATIONS_ES,
)
from tradeschool.exercises.types import ExerciseType  # noqa: E402

#: The repo root, and the two trees this script bridges.
REPO = _BACKEND.parent
CONTENT_DIR = REPO / "content"
FRONTEND_DIR = REPO / "frontend"
DEFAULT_OUT = REPO / "dist" / "bundle"

#: Bumped when the bundle's SHAPE changes in a way a shipped app would misread. Content changes move
#: the fingerprint, not this: an app pins the format it can parse and the fingerprint it last saw.
#:
#: v2 (2026-09-04) — three changes, one of them breaking. Per-lesson `summary` in the manifest; a new
#: `exercises/references.json`; and a calculation's `params` become an ORDERED LIST where they were a
#: map, which is the breaking one and the reason this is a version bump rather than an additive
#: release. `docs/bundle-format-changelog.md` is the full account and `docs/bundle-v2-app-spec.md` is
#: what the Android app has to do to consume it.
BUNDLE_FORMAT_VERSION = 2

#: The AST export's multiset text diff goes in a sibling `reports/` directory, never inside the
#: bundle: it is a verification report ABOUT the bundle, not content the app reads, and everything
#: inside `dist/bundle` crosses into the Android repository.
def diff_report_path(out: Path) -> Path:
    return out.parent / "reports" / "bundle-text-diff.json"


#: Where the TypeScript half writes the resolved references it finds in exercise prose. Named here
#: because both halves address it: this script asks for it and then checks every offset in it.
EXERCISE_REFS_FILE = "exercises/references.json"

#: `figure-coupling.yaml` goes in verbatim, under its own name — it is a reviewed content file, and
#: the app's own figure/prose agreement checks (should it ever grow them) read the same declarations.
VERBATIM_FILES = ("figure-coupling.yaml",)

# --- the closed block inventory -------------------------------------------------------------------

#: Depth an app heading style exists for. `####` in a lesson is an authoring accident, not a level.
MAX_HEADING_DEPTH = 3

#: The three callout tones `markdown.tsx` has a palette for; anything else renders untoned.
CALLOUT_TONES = ("info", "warning", "tip")

#: The two block slots the app fills with something it generates itself.
LEAF_SLOTS = ("figure", "exercise")

#: GFM's column alignments. `None` is "no marker", which is the default and what all of today's
#: tables use; the other three are `|:--|`, `|:-:|` and `|--:|`.
TABLE_ALIGNMENTS = (None, "left", "center", "right")

#: Every mdast node kind the app can render, and what makes each one valid.
#:
#: Closed on purpose. The keys are the whole vocabulary a lesson may use; `inventory_violations`
#: rejects any node kind not listed here, which is what stops a future lesson from shipping a block
#: the app draws as blank space. Adding a kind means building its renderer first, then adding it here.
BLOCK_INVENTORY: dict[str, str] = {
    "root": "the lesson itself",
    "heading": f"h1-h{MAX_HEADING_DEPTH}",
    "paragraph": "a paragraph of prose",
    "text": "literal characters",
    "strong": "bold",
    "emphasis": "italic",
    "inlineCode": "a code span inside a sentence",
    "list": "a bullet (ordered=false) or numbered (ordered=true) list",
    "listItem": "one item of either list",
    "blockquote": "a quotation",
    "table": "a GFM table, with per-column alignment",
    "tableRow": "one row of a table",
    "tableCell": "one cell of a row",
    "containerDirective": f":::note{{type={'|'.join(CALLOUT_TONES)}}} — a callout",
    "leafDirective": f"::{{{'|'.join(LEAF_SLOTS)}}}{{id=…}} — a generated slot",
    "glossaryTerm": "a glossary mark planted by the annotator",
    "lessonRef": "a lesson/module reference mark planted by the annotator",
}


def _walk(node: dict[str, Any], path: str) -> Iterator[tuple[dict[str, Any], str]]:
    yield node, path
    for index, child in enumerate(node.get("children") or []):
        kind = child.get("type", "?") if isinstance(child, dict) else "?"
        yield from _walk(child, f"{path}/{index}:{kind}")


def inventory_violations(
    tree: dict[str, Any], *, where: str, figures: Iterable[str], exercises: Iterable[str]
) -> list[str]:
    """Every way this lesson's AST leaves what the app can render. Empty list = shippable.

    `figures` and `exercises` are the ids that exist, because a slot naming neither is a blank space
    on the page rather than an error the app could report.
    """
    figure_ids, exercise_ids = set(figures), set(exercises)
    found: list[str] = []

    def fail(path: str, message: str) -> None:
        found.append(f"{where} {path}: {message}")

    for node, path in _walk(tree, tree.get("type", "?")):
        kind = node.get("type")
        if kind not in BLOCK_INVENTORY:
            fail(path, f"node kind {kind!r} is outside the block inventory")
            continue
        if kind == "heading":
            depth = node.get("depth")
            if depth not in range(1, MAX_HEADING_DEPTH + 1):
                fail(path, f"heading depth {depth!r} is deeper than h{MAX_HEADING_DEPTH}")
        elif kind == "list":
            if not isinstance(node.get("ordered"), bool):
                fail(path, f"list has no ordered flag ({node.get('ordered')!r})")
        elif kind == "table":
            for column in node.get("align") or []:
                if column not in TABLE_ALIGNMENTS:
                    fail(path, f"table column alignment {column!r} is not GFM")
        elif kind == "containerDirective":
            if node.get("name") != "note":
                fail(path, f"container directive {node.get('name')!r} has no renderer")
            tone = (node.get("attributes") or {}).get("type")
            if tone is not None and tone not in CALLOUT_TONES:
                fail(path, f"callout tone {tone!r} has no palette")
        elif kind == "leafDirective":
            name = node.get("name")
            slot_id = (node.get("attributes") or {}).get("id")
            if name not in LEAF_SLOTS:
                fail(path, f"leaf directive {name!r} has no renderer")
            elif not slot_id:
                fail(path, f"{name} slot carries no id")
            elif name == "figure" and slot_id not in figure_ids:
                fail(path, f"figure slot names {slot_id!r}, which no figure spec defines")
            elif name == "exercise" and slot_id not in exercise_ids:
                fail(path, f"exercise slot names {slot_id!r}, which the manifest does not declare")
        elif kind == "glossaryTerm":
            if not node.get("termId"):
                fail(path, "glossary mark carries no termId, so it would open nothing")
        elif kind == "lessonRef":
            if node.get("refKind") not in ("module", "lesson"):
                fail(path, f"reference mark kind {node.get('refKind')!r} is neither module nor lesson")
            if not node.get("refId"):
                fail(path, "reference mark carries no refId")
        elif kind in ("text", "inlineCode"):
            if not isinstance(node.get("value"), str):
                fail(path, f"{kind} carries no string value")
        # `data.hName` is `remarkDirectiveToHast`'s work: its presence means the export tapped the
        # pipeline one plugin too late and is shipping instructions for a DOM the app does not have.
        if "hName" in (node.get("data") or {}) and kind in ("containerDirective", "leafDirective"):
            fail(path, "carries a hast hint (data.hName) — the AST tap point moved past the annotator")
    return found


# --- canonical bytes and the fingerprint ----------------------------------------------------------


def canonical_bytes(value: object) -> bytes:
    """The bundle's one serialization: sorted keys, no spaces, real UTF-8, one trailing newline.

    The same recipe the committed golden fingerprints hash (`sort_keys`, `(",", ":")`), with
    `ensure_ascii` off so the TypeScript half writes byte-identical files — `JSON.stringify` has no
    escaping mode to match `\\uXXXX` output.
    """
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    ) + b"\n"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_fingerprint(files: dict[str, str]) -> str:
    """One digest over the whole bundle: sha256 of the canonical `{relative path: file sha256}` map.

    Over the map rather than over the bytes, so it is reproducible from `manifest.json` alone: a
    reader with the manifest can verify every file, then verify that the set of files is the one the
    fingerprint was taken over.
    """
    return hashlib.sha256(canonical_bytes(dict(sorted(files.items())))).hexdigest()


# --- the Python half ------------------------------------------------------------------------------


def load_content_registry(content_dir: Path = CONTENT_DIR) -> CourseRegistry:
    """The registry this backend builds at startup, with the same validation and no second reader."""
    return load_registry(content_dir)


def _localized(text: Any) -> dict[str, str]:
    return {locale: text.get(locale) for locale in LOCALES}


def build_manifest(registry: CourseRegistry, *, files: dict[str, str]) -> dict[str, Any]:
    """Identity, ordering and structure — plus the digest of every other file in the bundle."""
    manifest = registry.manifest
    blocks: list[dict[str, Any]] = []
    for block_order, block in enumerate(manifest.blocks, start=1):
        modules: list[dict[str, Any]] = []
        for module_order, module in enumerate(block.modules, start=1):
            lessons: list[dict[str, Any]] = []
            for lesson_order, lesson in enumerate(module.lessons, start=1):
                lessons.append(
                    {
                        "id": lesson.id,
                        "key": lesson.key,
                        "order": lesson_order,
                        "title": _localized(lesson.title),
                        "summary": _localized(lesson.summary),
                        "exercises": [
                            {
                                "id": exercise.id,
                                "key": exercise.key,
                                "order": exercise_order,
                                "type": exercise.type.value,
                                "playable": exercise.id in registry.exercise_configs,
                            }
                            for exercise_order, exercise in enumerate(lesson.exercises, start=1)
                        ],
                    }
                )
            modules.append(
                {
                    "id": module.id,
                    "key": module.key,
                    "order": module_order,
                    "title": _localized(module.title),
                    "summary": _localized(module.summary),
                    "assumes": list(module.assumes),
                    "lessons": lessons,
                }
            )
        blocks.append(
            {
                "id": block.id,
                "key": block.id,  # a block's id doubles as its key (schema.py's namespace rule)
                "order": block_order,
                "title": _localized(block.title),
                "modules": modules,
            }
        )
    return {
        "bundleFormatVersion": BUNDLE_FORMAT_VERSION,
        "course": {
            "id": manifest.course.id,
            "key": manifest.course.id,
            "title": _localized(manifest.course.title),
            "subtitle": _localized(manifest.course.subtitle),
            "description": _localized(manifest.course.description),
        },
        "locales": list(LOCALES),
        "blocks": blocks,
        "figures": [
            {"id": spec.id, "key": spec.key, "kind": spec.kind, "panels": len(spec.panels)}
            for spec in (registry.figures[fid] for fid in sorted(registry.figures))
        ],
        "counts": {
            "blocks": len(manifest.blocks),
            "modules": len(manifest.iter_modules()),
            "lessons": len(manifest.iter_lessons()),
            "exercises": len(manifest.iter_exercises()),
            "playableExercises": len(registry.exercise_configs),
            "figures": len(registry.figures),
            "glossaryTerms": len(registry.glossary.terms),
        },
        # Every other file in the bundle, by sha256. `manifest.json` is absent because it carries the
        # fingerprint taken over this very map and cannot contain its own digest.
        "files": dict(sorted(files.items())),
        "contentFingerprint": content_fingerprint(files),
    }


def exported_config(exercise_type: ExerciseType, config: BaseModel) -> dict[str, Any]:
    """One config as the generator parsed it, with the one field whose ORDER the bundle would lose.

    `canonical_bytes` sorts every key it serializes, which is what makes the fingerprint reproducible
    — and what silently rewrites a calculation's `params`. `calculation._sample_params` draws one
    value per parameter from ONE seeded rng, walking them in declaration order, so the order IS the
    question asked: nine of the eighteen calculation YAMLs declare a non-alphabetical order, and a
    port reading a sorted dict samples a different exercise from the same seed. m23-ex-5 changes four
    of its seven parameters that way, `style` among them.

    So they leave as an ordered LIST. A list survives key sorting, and a port that ignores the change
    fails to parse rather than quietly asking the wrong question — which is the only reason to prefer
    it to an `order` field beside the dict.
    """
    document: dict[str, Any] = config.model_dump(mode="json")
    if exercise_type is ExerciseType.CALCULATION:
        document["params"] = [{"name": name, **spec} for name, spec in document["params"].items()]
    return document


def build_exercise_configs(registry: CourseRegistry) -> dict[str, Any]:
    """All 147 configs as the generators parsed them, so the port validates against the same shape."""
    return {
        "configs": {
            exercise_id: {
                "type": exercise_type.value,
                "config": exported_config(exercise_type, config),
            }
            for exercise_id, (exercise_type, config) in sorted(registry.exercise_configs.items())
        }
    }


def build_figure_specs(registry: CourseRegistry) -> dict[str, Any]:
    """Seeds and parameters, never a rendered series — the app draws the chart from the spec."""
    figures: dict[str, Any] = {}
    for figure_id in sorted(registry.figures):
        spec = registry.figures[figure_id]
        entry: dict[str, Any] = {
            "id": spec.id,
            "key": spec.key,
            "kind": spec.kind,
            "caption": _localized(spec.caption),
            "panels": [panel.model_dump(mode="json") for panel in spec.panels],
        }
        if spec.kind == "svg":
            # An explicit marker, not an empty chart: this figure has no numerics at all and the app
            # must render a named component. Silence here would read as "a chart with no panels yet".
            entry["marker"] = "svg-component"
            entry["svg"] = spec.svg
        figures[figure_id] = entry
    return {"figures": figures}


def build_reading_seconds(registry: CourseRegistry) -> dict[str, Any]:
    """The 88 integers, exported. Derived once from the markdown here; never recomputed on a phone."""
    return {
        "readingSeconds": {
            locale: {
                lesson.id: registry.lesson_reading_seconds(lesson.id, locale)
                for _module, lesson in registry.manifest.iter_lessons()
            }
            for locale in LOCALES
        }
    }


def build_error_phrases() -> dict[str, Any]:
    """The named-mistake phrase a wrong calculation answer is diagnosed with, in both locales.

    The EN phrase IS the key: it is authored as the distractor's label in `formulas.py` and
    `MISTAKE_TRANSLATIONS_ES` is keyed on it, which is why there is one table and not two that could
    disagree about which mistakes exist. That every reachable label has an ES entry is asserted by
    `tests/test_exercise_numbers.py::test_every_named_mistake_can_be_stated_in_spanish`.
    """
    return {
        "kind": "calculation-error-phrases",
        "keyedBy": "en",
        # The sentence the phrase is printed in, so the app stops writing its own. `{value}` is the
        # option the learner picked, `{mistake}` the phrase below in their language. The two locales
        # are different shapes on purpose — see `calculation.MISTAKE_SENTENCES`.
        "sentences": dict(sorted(MISTAKE_SENTENCES.items())),
        "phrases": [
            {"key": english, "en": english, "es": spanish}
            for english, spanish in sorted(MISTAKE_TRANSLATIONS_ES.items())
        ],
    }


def build_glossary(registry: CourseRegistry, locale: str) -> dict[str, Any]:
    """One locale's entries in that locale's own alphabetical order, as the export endpoint serves them."""
    return {"locale": locale, "entries": registry.glossary_entries(locale)}


def build_readme(counts: dict[str, int]) -> str:
    """A map of the bundle, generated — a reader of a hundred files should not have to infer the layout.

    It deliberately does NOT quote the content fingerprint: this file is itself digested into it, so a
    quoted value would be the one taken before this file existed, i.e. always stale by one export.
    """
    inventory = "\n".join(f"| `{kind}` | {what} |" for kind, what in sorted(BLOCK_INVENTORY.items()))
    summary = " · ".join(
        [
            f"{counts['blocks']} blocks",
            f"{counts['modules']} modules",
            f"{counts['lessons']} lessons",
            f"{counts['exercises']} exercises ({counts['playableExercises']} playable)",
            f"{counts['figures']} figures",
            f"{counts['glossaryTerms']} glossary terms",
            f"locales {', '.join(LOCALES)}",
        ]
    )
    layout = "\n".join(
        f"| {path} | {what} |"
        for path, what in (
            (
                "`manifest.json`",
                "identity, ordering and block structure; every entity by display **id** and "
                "permanent **key**; the digest of every other file, and the fingerprint over that map",
            ),
            (
                "`ast/index.json`",
                "the lesson list, the per-locale node-type census, and the pipeline point the ASTs "
                "were taken at",
            ),
            ("`ast/<locale>/<lesson id>.json`", "one lesson's annotated mdast (see below)"),
            (
                "`glossary/glossary.<locale>.json`",
                "every term, in that locale's own alphabetical order",
            ),
            (
                "`exercises/configs.json`",
                f"all {counts['exercises']} generator configs, as the generators parsed them",
            ),
            (
                "`figures/specs.json`",
                f"all {counts['figures']} figure specs: injector, parameters, frozen seed — "
                "never a rendered series",
            ),
            (
                "`reading-seconds.json`",
                "the per-(lesson, locale) reading estimate, exported rather than recomputed",
            ),
            ("`error-phrases.json`", "the calculation named-mistake phrases, both locales"),
            (
                "`figure-coupling.yaml`",
                "copied verbatim: which lesson numbers approximate which figure's generated values",
            ),
        )
    )
    return f"""<!-- SPDX-License-Identifier: AGPL-3.0-only -->
# TradeSchool content bundle

Generated by `backend/scripts/export_bundle.py` in the TradeSchool web repository. Do not hand-edit
any of it: regenerate, and read the diff.

This is the whole course as the native app reads it — no backend, no network. Bundle format version
**{BUNDLE_FORMAT_VERSION}**; the content fingerprint is `contentFingerprint` in `manifest.json`, and
is not repeated here because this file is digested into it.

Version 2 adds a per-lesson `summary` to the manifest and an `exercises/references.json`, and changes
a calculation config's `params` from a map to an ORDERED LIST — the order is the question asked, and a
map loses it to key sorting. A v1 reader must not parse a v2 bundle.

{summary}

## Layout

| path | what it is |
| --- | --- |
{layout}

## The lesson ASTs

Each file is `{{"lessonId", "lessonKey", "locale", "ast"}}`, where `ast` is the mdast **after** the
glossary/lesson-reference annotator and **before** the hast hints — so `glossaryTerm` and `lessonRef`
marks are already planted (web policy: first occurrence per lesson) and `::figure` / `::exercise` are
still directive nodes, not `<div data-figure-id>`. Source positions are stripped.

Marks are planted by ONE annotator (`frontend/src/lib/glossary/annotate.ts`) whose decisions are
frozen in `content/glossary-links.<locale>.txt` and `content/lesson-refs.<locale>.txt`. Do not
re-detect terms in the app: a second detector is a second opinion about which words a reader may tap.

## The closed block inventory

The export refuses to write a bundle containing any other node kind, because an unrenderable node is
a hole in the page and nothing downstream can notice it. Heading depth is capped at
h{MAX_HEADING_DEPTH}; callout tones are {", ".join(f"`{t}`" for t in CALLOUT_TONES)}; slots are
{", ".join(f"`::{s}`" for s in LEAF_SLOTS)} and each must name something that exists.

| node kind | renders as |
| --- | --- |
{inventory}

## Verifying this bundle

Every file's sha256 is in `manifest.json` under `files`, and `contentFingerprint` is the sha256 of
the canonical JSON of that map. `manifest.json` is the one file not in its own list, because it
carries the digest taken over that very map and cannot contain its own.

**The canonical bytes, in full** — this is the serialization every file in the bundle is written
with, and a port reproduces the fingerprint from this description alone:

1. the map is `{{relative POSIX path: sha256 hex}}`, with **sorted keys**;
2. `(",", ":")` **separators** — no space after either;
3. encoded **UTF-8**, writing non-ASCII characters as themselves rather than `\\uXXXX` escapes;
4. then **one trailing newline** (`0x0A`) appended to those bytes before hashing.

Step 4 is the one a port drops, and it is invisible: hashing without it yields a completely
different digest that looks just as plausible. The whole recipe, in Python:

```python
sha256(
    json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    + b"\\n"
)
```

This is **not** the recipe behind the digests in `contracts/generation-goldens/`, which hashes
ASCII-escaped bytes with no trailing newline and is frozen by fingerprints committed in the web
repo's suite. The two are separate on purpose: a port needs both and must not share one serializer
between them.

The export also proves, per locale, that the words in these ASTs and in this glossary are exactly the
words the web serves from the same content — a multiset diff that must come out empty — and that each
lesson matches the page the web paints block for block and in order, whitespace included. See
`docs/verification-blind-spots.md` in the web repo.
"""


def localized_strings(node: object, path: str = "") -> Iterator[tuple[str, dict[str, str]]]:
    """Every `{en, es}` pair inside a config, with the path that carries it.

    Generic rather than a list of per-generator field names: a new exercise type's prose is exercise
    prose the day it is authored, and a hand-kept list would leave it unannotated until somebody
    remembered to extend it. The path addresses the EXPORTED config, so it reads straight into
    `exercises/configs.json`.
    """
    if isinstance(node, dict):
        if set(node) == set(LOCALES) and all(isinstance(value, str) for value in node.values()):
            yield path, {locale: node[locale] for locale in LOCALES}
            return
        for key, value in node.items():
            yield from localized_strings(value, f"{path}.{key}" if path else str(key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from localized_strings(value, f"{path}[{index}]")


def build_ast_input(registry: CourseRegistry) -> dict[str, Any]:
    """What the TypeScript half needs, so it never reads `content/` or knows the manifest's shape.

    Two markdowns per lesson and the difference is the point: `markdown` is what the app renders
    (exercise slots included) and `exportMarkdown` is what `/export` serves (theory only), which is
    the reference the multiset text diff compares the bundle against.
    """
    lessons = [
        {
            "id": lesson.id,
            "key": lesson.key,
            "moduleId": module.id,
            "markdown": {loc: registry.markdown[loc][lesson.id] for loc in LOCALES},
            "exportMarkdown": {
                loc: _theory_only(registry.markdown[loc][lesson.id]) for loc in LOCALES
            },
        }
        for module, lesson in registry.manifest.iter_lessons()
    ]
    return {
        "locales": list(LOCALES),
        "lessons": lessons,
        "modules": {
            locale: [
                {
                    "id": module.id,
                    "key": module.key,
                    "title": module.title.get(locale),
                    "lessons": [
                        {"id": lesson.id, "key": lesson.key, "title": lesson.title.get(locale)}
                        for lesson in module.lessons
                    ],
                }
                for _block, module in registry.manifest.iter_modules()
            ]
            for locale in LOCALES
        },
        "glossary": {locale: registry.glossary_entries(locale) for locale in LOCALES},
        # Exercise prose names modules by id ("the spring of m09"), and until now only LESSON prose
        # arrived at the app with those resolved — so the app carried a second detector to find them
        # (`ExerciseReferences.kt`'s own regex). These are every localized string in every config,
        # addressed by the path they sit at in `exercises/configs.json`.
        "exerciseTexts": [
            {"exerciseId": exercise_id, "path": path, "text": text}
            for exercise_id, (exercise_type, config) in sorted(registry.exercise_configs.items())
            for path, text in localized_strings(exported_config(exercise_type, config))
        ],
    }


# --- the export ------------------------------------------------------------------------------------


class BundleError(RuntimeError):
    """The bundle would have shipped something the app cannot render, or cannot be trusted to carry."""


def _write(out: Path, relative: str, payload: object) -> None:
    path = out / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(payload))


def _bundle_files(out: Path) -> dict[str, str]:
    return {
        path.relative_to(out).as_posix(): sha256_file(path)
        for path in sorted(out.rglob("*"))
        if path.is_file() and path.name != "manifest.json" and not path.name.startswith(".")
    }


def _run_ast_export(out: Path, *, verify: bool, emit: bool = True) -> None:
    ast_input = out / ".ast-input.json"
    report = diff_report_path(out)
    report.parent.mkdir(parents=True, exist_ok=True)
    (out / "exercises").mkdir(parents=True, exist_ok=True)
    command = [
        "npm", "run", "--silent", "export:bundle-ast", "--",
        "--input", str(ast_input),
        "--out", str(out / "ast"),
        "--glossary-dir", str(out / "glossary"),
        "--refs-out", str(out / EXERCISE_REFS_FILE),
        "--diff-report", str(report),
    ]
    if not verify:
        command.append("--no-verify")
    if not emit:
        command.append("--verify-only")
    print(f"  $ (cd frontend && {' '.join(command[:5])} ...)", flush=True)
    try:
        result = subprocess.run(command, cwd=FRONTEND_DIR, check=False)
    except FileNotFoundError as exc:  # pragma: no cover - environment, not logic
        raise BundleError(
            "npm was not found. The lesson ASTs are built by the frontend toolchain "
            "(frontend/scripts/export-ast.mjs); run `npm install` in frontend/, or pass --skip-ast "
            "to export only the Python half."
        ) from exc
    if result.returncode != 0:
        raise BundleError(f"the AST export failed (exit {result.returncode}) — see its output above")


def _check_inventory(out: Path, registry: CourseRegistry) -> int:
    exercises = {exercise.id for _m, _l, exercise in registry.manifest.iter_exercises()}
    violations: list[str] = []
    checked = 0
    for locale in LOCALES:
        directory = out / "ast" / locale
        if not directory.is_dir():
            raise BundleError(f"no ASTs for {locale!r} at {directory} — did the AST export run?")
        for path in sorted(directory.glob("*.json")):
            document = json.loads(path.read_text(encoding="utf-8"))
            violations.extend(
                inventory_violations(
                    document["ast"],
                    where=f"{locale}/{document['lessonId']}",
                    figures=registry.figures,
                    exercises=exercises,
                )
            )
            checked += 1
    if violations:
        shown = "\n  ".join(violations[:40])
        more = "" if len(violations) <= 40 else f"\n  ... and {len(violations) - 40} more"
        raise BundleError(
            f"{len(violations)} node(s) outside the block inventory — the app renders these as "
            f"nothing, so the bundle is not written:\n  {shown}{more}"
        )
    return checked


def _check_exercise_refs(out: Path, registry: CourseRegistry) -> int:
    """Every mark's offsets must cut the mention out of the string the bundle actually carries.

    The TypeScript half reads them back against its own input; this reads them back against the file
    that shipped. Two different strings would mean the config was written from one content version
    and the marks from another, which is precisely the split-brain a two-step export has and this
    one-command export exists to prevent — and it would land as a chip on the wrong word.
    """
    document = json.loads((out / EXERCISE_REFS_FILE).read_text(encoding="utf-8"))
    configs = json.loads((out / "exercises" / "configs.json").read_text(encoding="utf-8"))["configs"]
    texts = {
        (exercise_id, path): text
        for exercise_id, entry in configs.items()
        for path, text in localized_strings(entry["config"])
    }
    violations: list[str] = []
    checked = 0
    for exercise_id, by_locale in document["references"].items():
        for locale, by_path in by_locale.items():
            for path, marks in by_path.items():
                source = texts.get((exercise_id, path), {}).get(locale)
                if source is None:
                    violations.append(f"{exercise_id} {locale} {path}: no such string in configs.json")
                    continue
                for mark in marks:
                    cut = source[mark["start"] : mark["end"]]
                    if cut != mark["mention"]:
                        violations.append(
                            f"{exercise_id} {locale} {path}: offsets name {cut!r}, "
                            f"mark says {mark['mention']!r}"
                        )
                    checked += 1
    if violations:
        shown = "\n  ".join(violations[:20])
        raise BundleError(
            f"{len(violations)} exercise reference(s) do not sit where their offsets say:\n  {shown}"
        )
    known = {exercise.id for _m, _l, exercise in registry.manifest.iter_exercises()}
    unknown = sorted(set(document["references"]) - known)
    if unknown:
        raise BundleError(f"exercise references for exercises the manifest does not declare: {unknown}")
    return checked


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"default {DEFAULT_OUT}")
    parser.add_argument("--content", type=Path, default=CONTENT_DIR, help=f"default {CONTENT_DIR}")
    parser.add_argument(
        "--skip-ast", action="store_true", help="write only the Python half (no node/npm needed)"
    )
    parser.add_argument(
        "--no-verify", action="store_true", help="skip the multiset text diff against the web export"
    )
    parser.add_argument(
        "--verify-only", action="store_true",
        help="re-check an existing bundle (inventory + text diff) without rewriting it",
    )
    args = parser.parse_args(argv)

    out: Path = args.out
    started = time.monotonic()
    registry = load_content_registry(args.content)

    if args.verify_only:
        if not (out / "manifest.json").exists():
            raise BundleError(f"no bundle at {out} to verify")
        print(f"verifying the bundle at {out} ...", flush=True)
        _write(out, ".ast-input.json", build_ast_input(registry))
        _run_ast_export(out, verify=not args.no_verify, emit=False)
        checked = _check_inventory(out, registry)
        print(f"block inventory   OK  ({checked} lesson ASTs)")
        marks = _check_exercise_refs(out, registry)
        print(f"exercise refs     OK  ({marks} marks, offsets read back from the shipped strings)")
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        current = _bundle_files(out)
        if current != manifest["files"]:
            drift = sorted(set(current) ^ set(manifest["files"])) or [
                key for key in current if current[key] != manifest["files"].get(key)
            ]
            raise BundleError(f"the bundle no longer matches its manifest: {drift[:10]}")
        print(f"fingerprint       {manifest['contentFingerprint']}  (verified against {len(current)} files)")
        (out / ".ast-input.json").unlink(missing_ok=True)
        return 0

    print(f"exporting the bundle to {out} ...", flush=True)
    if out.exists():
        shutil.rmtree(out)  # a stale lesson left behind is a bundle shipping two versions of a page
    out.mkdir(parents=True)

    for locale in LOCALES:
        _write(out, f"glossary/glossary.{locale}.json", build_glossary(registry, locale))
    _write(out, "exercises/configs.json", build_exercise_configs(registry))
    _write(out, "figures/specs.json", build_figure_specs(registry))
    _write(out, "reading-seconds.json", build_reading_seconds(registry))
    _write(out, "error-phrases.json", build_error_phrases())
    for name in VERBATIM_FILES:
        shutil.copyfile(args.content / name, out / name)

    if args.skip_ast:
        print("  (--skip-ast: the lesson ASTs and the text diff were not produced)")
    else:
        _write(out, ".ast-input.json", build_ast_input(registry))
        _run_ast_export(out, verify=not args.no_verify)
        checked = _check_inventory(out, registry)
        print(f"block inventory   OK  ({checked} lesson ASTs, {len(BLOCK_INVENTORY)} allowed kinds)")
        marks = _check_exercise_refs(out, registry)
        print(f"exercise refs     OK  ({marks} marks, offsets read back from the shipped strings)")
        (out / ".ast-input.json").unlink(missing_ok=True)

    (out / "README.md").write_text(
        build_readme(build_manifest(registry, files={})["counts"]), encoding="utf-8"
    )
    files = _bundle_files(out)
    manifest = build_manifest(registry, files=files)
    _write(out, "manifest.json", manifest)

    counts = manifest["counts"]
    print()
    print("=" * 78)
    print(f"BUNDLE FINGERPRINT  {manifest['contentFingerprint']}")
    print("=" * 78)
    print(f"format version    {BUNDLE_FORMAT_VERSION}")
    print(f"files             {len(files)} (+ manifest.json)")
    print(
        "content           "
        f"{counts['blocks']} blocks · {counts['modules']} modules · {counts['lessons']} lessons · "
        f"{counts['exercises']} exercises · {counts['figures']} figures · "
        f"{counts['glossaryTerms']} glossary terms"
    )
    print(f"locales           {', '.join(LOCALES)}")
    print(f"elapsed           {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BundleError as error:
        print(f"\nBUNDLE EXPORT FAILED\n{error}", file=sys.stderr)
        raise SystemExit(2) from None
