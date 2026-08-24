# SPDX-License-Identifier: AGPL-3.0-only
"""The Android bundle's contracts: the closed block inventory, and what the bundle must carry.

Phase W2. The bundle is the content the native app reads instead of calling this backend, so every
guarantee the web makes by *rendering* has to become a guarantee the bundle makes by *validation*.

The load-bearing one is the **block inventory**. The app can render exactly the node kinds listed in
`BLOCK_INVENTORY` and nothing else, and a lesson that acquires a fenced code block, an image, a
hard line break or a fourth-level heading would ship as a hole in the page rather than as an error.
There is no way for the app to notice — an unknown mdast node simply renders as nothing — so the
export refuses to write a bundle containing one. Everything below asserts that the refusal actually
happens, node kind by node kind, because a vaccine that says yes to everything is worse than none.

The rest is the inventory of what the bundle must CARRY: the 147 exercise configs as the engine
consumes them, the 34 figure specs (seeds, not pixels), the 88 reading-time integers exported rather
than recomputed on a phone, the bilingual calculation error-phrase table, and a manifest whose
fingerprint covers every other file in the bundle.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import pytest

_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.export_bundle import (  # noqa: E402
    BLOCK_INVENTORY,
    BUNDLE_FORMAT_VERSION,
    CALLOUT_TONES,
    LEAF_SLOTS,
    MAX_HEADING_DEPTH,
    build_error_phrases,
    build_exercise_configs,
    build_figure_specs,
    build_glossary,
    build_manifest,
    build_readme,
    build_reading_seconds,
    canonical_bytes,
    content_fingerprint,
    inventory_violations,
    load_content_registry,
)

# --- a tree that uses every allowed node kind, which is the inventory written as data -------------


def _text(value: str) -> dict[str, Any]:
    return {"type": "text", "value": value}


def _paragraph(*children: dict[str, Any]) -> dict[str, Any]:
    return {"type": "paragraph", "children": list(children)}


def _full_tree() -> dict[str, Any]:
    """One lesson exercising the whole inventory — h1-h3, both lists, a table, both marks, both slots."""
    return {
        "type": "root",
        "children": [
            {"type": "heading", "depth": 1, "children": [_text("Title")]},
            {"type": "heading", "depth": 2, "children": [_text("Section")]},
            {"type": "heading", "depth": 3, "children": [_text("Sub")]},
            _paragraph(
                _text("plain "),
                {"type": "strong", "children": [_text("bold")]},
                {"type": "emphasis", "children": [_text("italic")]},
                {"type": "inlineCode", "value": "Decimal"},
                {
                    "type": "glossaryTerm",
                    "termId": "g-funding",
                    "children": [_text("funding")],
                    "data": {"hName": "span", "hProperties": {"data-term-id": "g-funding"}},
                },
                {
                    "type": "lessonRef",
                    "refKind": "module",
                    "refId": "m22",
                    "children": [_text("m22")],
                    "data": {
                        "hName": "span",
                        "hProperties": {"data-ref-kind": "module", "data-ref-id": "m22"},
                    },
                },
            ),
            {
                "type": "list",
                "ordered": False,
                "spread": False,
                "children": [{"type": "listItem", "spread": False, "children": [_paragraph(_text("a"))]}],
            },
            {
                "type": "list",
                "ordered": True,
                "start": 1,
                "spread": False,
                "children": [{"type": "listItem", "spread": False, "children": [_paragraph(_text("b"))]}],
            },
            {"type": "blockquote", "children": [_paragraph(_text("quoted"))]},
            {
                "type": "table",
                "align": [None, "left", "center", "right"],
                "children": [
                    {
                        "type": "tableRow",
                        "children": [
                            {"type": "tableCell", "children": [_text("h1")]},
                            {"type": "tableCell", "children": [_text("h2")]},
                            {"type": "tableCell", "children": [_text("h3")]},
                            {"type": "tableCell", "children": [_text("h4")]},
                        ],
                    }
                ],
            },
            {
                "type": "containerDirective",
                "name": "note",
                "attributes": {"type": "warning"},
                "children": [_paragraph(_text("careful"))],
            },
            {
                "type": "leafDirective",
                "name": "figure",
                "attributes": {"id": "fig-known"},
                "children": [],
            },
            {
                "type": "leafDirective",
                "name": "exercise",
                "attributes": {"id": "ex-known"},
                "children": [],
            },
        ],
    }


_KNOWN = {"figures": {"fig-known"}, "exercises": {"ex-known"}}


def _violations(tree: dict[str, Any]) -> list[str]:
    return inventory_violations(tree, where="es/test-lesson", **_KNOWN)


def test_a_tree_using_the_whole_inventory_is_accepted() -> None:
    """The positive case, first: a vaccine that rejects everything proves nothing about the rest."""
    assert _violations(_full_tree()) == []


def test_the_inventory_is_closed_and_names_every_kind_the_tree_above_uses() -> None:
    """The constant IS the contract, so it is asserted against the tree rather than trusted."""
    used: set[str] = set()

    def walk(node: dict[str, Any]) -> None:
        used.add(node["type"])
        for child in node.get("children", []):
            walk(child)

    walk(_full_tree())
    assert used == set(BLOCK_INVENTORY), "the exhaustive tree and the inventory have drifted apart"


# --- the vaccine: one test per way future content could break the app ----------------------------


@pytest.mark.parametrize(
    ("name", "node"),
    [
        ("fenced code", {"type": "code", "lang": "python", "value": "x = 1"}),
        ("image", {"type": "image", "url": "chart.png", "children": []}),
        ("link", {"type": "link", "url": "https://x", "children": [_text("x")]}),
        ("hard break", {"type": "break"}),
        ("thematic break", {"type": "thematicBreak"}),
        ("raw html", {"type": "html", "value": "<div>"}),
        ("strikethrough", {"type": "delete", "children": [_text("gone")]}),
        ("footnote", {"type": "footnoteReference", "identifier": "1"}),
        ("front matter", {"type": "yaml", "value": "a: 1"}),
    ],
)
def test_a_block_the_app_cannot_render_fails_loudly(name: str, node: dict[str, Any]) -> None:
    tree = _full_tree()
    tree["children"].append(node)
    found = _violations(tree)
    assert found, f"a {name} node slipped through the inventory"
    assert any(node["type"] in message for message in found), found
    assert all("es/test-lesson" in message for message in found), "a violation must name its lesson"


def test_a_heading_deeper_than_h3_fails() -> None:
    tree = _full_tree()
    tree["children"].append({"type": "heading", "depth": 4, "children": [_text("too deep")]})
    assert any("depth" in message for message in _violations(tree))
    assert MAX_HEADING_DEPTH == 3


def test_an_inline_directive_fails_because_the_dialect_is_deleted() -> None:
    """`03:00` used to parse as a `:00` directive; the parser drops the construct and so does this."""
    tree = _full_tree()
    tree["children"].append(
        _paragraph({"type": "textDirective", "name": "00", "attributes": {}, "children": []})
    )
    assert any("textDirective" in message for message in _violations(tree))


def test_a_callout_tone_the_app_has_no_palette_for_fails() -> None:
    tree = _full_tree()
    tree["children"].append(
        {
            "type": "containerDirective",
            "name": "danger",
            "attributes": {"type": "danger"},
            "children": [_paragraph(_text("x"))],
        }
    )
    found = _violations(tree)
    assert any("danger" in message for message in found), found
    assert CALLOUT_TONES == ("info", "warning", "tip")


def test_a_leaf_slot_the_app_has_no_renderer_for_fails() -> None:
    tree = _full_tree()
    tree["children"].append(
        {"type": "leafDirective", "name": "video", "attributes": {"id": "v1"}, "children": []}
    )
    assert any("video" in message for message in _violations(tree))
    assert LEAF_SLOTS == ("figure", "exercise")


def test_a_slot_naming_something_that_does_not_exist_fails() -> None:
    """A dangling figure or exercise slot is a blank space on the page, in the app as on the web."""
    tree = _full_tree()
    tree["children"].append(
        {"type": "leafDirective", "name": "figure", "attributes": {"id": "fig-ghost"}, "children": []}
    )
    tree["children"].append(
        {"type": "leafDirective", "name": "exercise", "attributes": {"id": "ex-ghost"}, "children": []}
    )
    found = _violations(tree)
    assert any("fig-ghost" in message for message in found), found
    assert any("ex-ghost" in message for message in found), found


def test_a_table_alignment_outside_gfm_fails() -> None:
    tree = _full_tree()
    tree["children"].append(
        {
            "type": "table",
            "align": ["justify"],
            "children": [
                {"type": "tableRow", "children": [{"type": "tableCell", "children": [_text("x")]}]}
            ],
        }
    )
    assert any("justify" in message for message in _violations(tree))


def test_a_mark_without_its_target_fails() -> None:
    """A glossary mark whose `termId` is gone renders as a tappable word that opens nothing."""
    tree = _full_tree()
    tree["children"].append(_paragraph({"type": "glossaryTerm", "children": [_text("x")]}))
    tree["children"].append(
        _paragraph({"type": "lessonRef", "refKind": "wormhole", "refId": "m99", "children": [_text("x")]})
    )
    found = _violations(tree)
    assert any("termId" in message for message in found), found
    assert any("wormhole" in message for message in found), found


def test_a_hast_hint_on_a_directive_means_the_tap_point_moved() -> None:
    """`data.hName` on a directive is `remarkDirectiveToHast`'s work, i.e. one plugin too far."""
    tree = _full_tree()
    tree["children"].append(
        {
            "type": "leafDirective",
            "name": "figure",
            "attributes": {"id": "fig-known"},
            "children": [],
            "data": {"hName": "div", "hProperties": {"data-figure-id": "fig-known"}},
        }
    )
    assert any("hName" in message for message in _violations(tree))


# --- what the bundle must carry -------------------------------------------------------------------


@pytest.fixture(scope="module")
def registry() -> Any:
    return load_content_registry()


def test_every_declared_exercise_config_is_exported_as_the_engine_consumes_it(registry: Any) -> None:
    configs = build_exercise_configs(registry)
    assert set(configs["configs"]) == set(registry.exercise_configs)
    assert len(configs["configs"]) == len(registry.manifest.iter_exercises())
    for exercise_id, entry in configs["configs"].items():
        declared = registry.exercise_configs[exercise_id]
        assert entry["type"] == declared[0].value
        assert entry["config"] == declared[1].model_dump(mode="json"), exercise_id
        assert "tolerance" not in entry["config"], f"{exercise_id}: the retired field came back"


def test_every_figure_is_exported_as_a_spec_and_never_as_pixels(registry: Any) -> None:
    figures = build_figure_specs(registry)
    assert set(figures["figures"]) == set(registry.figures)
    charts = {fid for fid, f in figures["figures"].items() if f["kind"] == "chart"}
    svgs = {fid for fid, f in figures["figures"].items() if f["kind"] == "svg"}
    assert charts and svgs, "both figure kinds must be represented"
    for fid in svgs:
        entry = figures["figures"][fid]
        assert entry["marker"] == "svg-component", fid
        assert entry["svg"], f"{fid}: an svg figure must name its component"
        assert entry["panels"] == []
    for fid in charts:
        entry = figures["figures"][fid]
        assert "marker" not in entry
        assert entry["panels"], fid
        for panel in entry["panels"]:
            assert isinstance(panel["seed"], int), fid
            assert panel["generator"] in {"pattern_chart", "synthetic_chart"}, fid
    # No rendered output anywhere: a spec carries a seed, never a series.
    assert "series" not in canonical_bytes(figures).decode()


def test_reading_seconds_are_exported_for_every_lesson_and_locale(registry: Any) -> None:
    reading = build_reading_seconds(registry)
    assert set(reading["readingSeconds"]) == {"en", "es"}
    lesson_ids = {lesson.id for _module, lesson in registry.manifest.iter_lessons()}
    total = 0
    for locale, per_lesson in reading["readingSeconds"].items():
        assert set(per_lesson) == lesson_ids
        for lesson_id, seconds in per_lesson.items():
            assert isinstance(seconds, int) and seconds > 0
            assert seconds == registry.lesson_reading_seconds(lesson_id, locale)
            total += 1
    assert total == 2 * len(lesson_ids)


def test_the_error_phrase_table_carries_both_locales(registry: Any) -> None:
    """A monolingual table would leave an ES learner reading their mistake in English."""
    table = build_error_phrases()
    assert table["phrases"], "the table is empty"
    for entry in table["phrases"]:
        assert entry["en"] and entry["es"], entry
        assert entry["key"] == entry["en"], "the EN phrase IS the key the ES table is keyed on"
        assert entry["es"] != entry["en"], entry


def test_the_glossary_is_exported_per_locale_in_that_locale_s_order(registry: Any) -> None:
    for locale in ("en", "es"):
        exported = build_glossary(registry, locale)
        assert exported["locale"] == locale
        assert exported["entries"] == registry.glossary_entries(locale)
        assert len(exported["entries"]) == len(registry.glossary.terms)
    assert [e["id"] for e in build_glossary(registry, "en")["entries"]] != [
        e["id"] for e in build_glossary(registry, "es")["entries"]
    ], "the two locales sort differently; identical order means one of them is wrong"


def test_the_manifest_carries_identity_in_both_spaces_and_the_whole_structure(registry: Any) -> None:
    manifest = build_manifest(registry, files={})
    assert manifest["bundleFormatVersion"] == BUNDLE_FORMAT_VERSION
    assert [b["id"] for b in manifest["blocks"]] == [b.id for b in registry.manifest.blocks]
    modules = [m for b in manifest["blocks"] for m in b["modules"]]
    lessons = [lesson for m in modules for lesson in m["lessons"]]
    exercises = [ex for lesson in lessons for ex in lesson["exercises"]]
    assert len(modules) == len(registry.manifest.iter_modules())
    assert len(lessons) == len(registry.manifest.iter_lessons())
    assert len(exercises) == len(registry.manifest.iter_exercises())
    for entity in [*modules, *lessons, *exercises]:
        assert entity["key"], entity
        assert entity["id"], entity
    assert [lesson["order"] for m in modules for lesson in m["lessons"]] == [
        index for m in modules for index in range(1, len(m["lessons"]) + 1)
    ]


def test_the_content_fingerprint_moves_with_any_file_and_covers_all_of_them(registry: Any) -> None:
    files = {"a.json": "0" * 64, "b/c.json": "1" * 64}
    baseline = content_fingerprint(files)
    assert len(baseline) == 64
    assert content_fingerprint(dict(reversed(list(files.items())))) == baseline, "order must not matter"
    assert content_fingerprint({**files, "b/c.json": "2" * 64}) != baseline
    assert content_fingerprint({**files, "d.json": "3" * 64}) != baseline


def test_the_manifest_fingerprint_excludes_only_the_manifest(registry: Any) -> None:
    """It cannot contain its own digest, and that exclusion is the one hole the reader must know about."""
    manifest = build_manifest(registry, files={"ast/index.json": "0" * 64})
    assert manifest["contentFingerprint"] == content_fingerprint({"ast/index.json": "0" * 64})
    assert "manifest.json" not in manifest["files"]


# --- the fingerprint recipe as the README states it ------------------------------------------------
#
# Every test above hashes by calling `content_fingerprint`, which compares the code to itself and so
# cannot see the recipe drift away from its documentation. The Android port has no such luxury: it
# implements this from `README.md` and never reads this file. So the two tests below hold the README
# to being a complete specification — an independent implementation written from its words alone
# reproduces the real digest, and the words that make that possible are actually present.

#: The recipe, reimplemented from `README.md`'s "Verifying this bundle" section and nothing else.
#: Deliberately does NOT call `canonical_bytes`: that would test the exporter against itself again.
def _fingerprint_from_documented_recipe(files: dict[str, str]) -> str:
    canonical = json.dumps(files, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8") + b"\n").hexdigest()


#: Each clause the README must carry for the reimplementation above to be derivable from it.
DOCUMENTED_RECIPE_CLAUSES = (
    "sorted keys",
    '`(",", ":")` separators',
    "UTF-8",
    "non-ASCII characters as themselves",
    "one trailing newline",
)


def test_the_documented_recipe_alone_reproduces_the_content_fingerprint(registry: Any) -> None:
    """A reader who implements only what the README says arrives at the committed digest.

    The trailing `\\n` is the clause this test exists for: `canonical_bytes` appends one, an
    unsuspecting `json.dumps(...).hexdigest()` does not, and the two digests differ completely.
    """
    files = {"a.json": "0" * 64, "b/c.json": "1" * 64, "ast/en/m01-l1.json": "2" * 64}
    assert _fingerprint_from_documented_recipe(files) == content_fingerprint(files)

    manifest = build_manifest(registry, files=files)
    assert _fingerprint_from_documented_recipe(manifest["files"]) == manifest["contentFingerprint"]


def test_the_readme_states_every_clause_the_recipe_needs(registry: Any) -> None:
    """The port implements this from prose, so a missing clause is a wrong digest on a phone."""
    readme = build_readme(build_manifest(registry, files={})["counts"])
    section = readme.split("## Verifying this bundle", 1)
    assert len(section) == 2, "the README lost the section that specifies the fingerprint"
    body = section[1]
    missing = [clause for clause in DOCUMENTED_RECIPE_CLAUSES if clause not in body]
    assert not missing, f"the fingerprint recipe no longer states: {missing}"
