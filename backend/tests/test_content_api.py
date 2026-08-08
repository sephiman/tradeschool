# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import json
from typing import Any

from httpx import AsyncClient

from tradeschool.config import get_settings
from tradeschool.content.registry import load_registry

CREDS = {"username": "student", "password": "correcthorse"}


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


def _module(course: dict[str, Any], module_id: str) -> dict[str, Any]:
    for block in course["blocks"]:
        for module in block["modules"]:
            if module["id"] == module_id:
                return module
    raise AssertionError(f"module {module_id} not in course")


async def test_course_requires_auth(content_client: AsyncClient) -> None:
    assert (await content_client.get("/api/course")).status_code == 401


async def test_course_export_theory_only(content_client: AsyncClient) -> None:
    assert (await content_client.get("/api/course/export")).status_code == 401  # requires a login
    await _auth(content_client)

    data = (await content_client.get("/api/course/export?lang=en")).json()
    assert data["locale"] == "en"
    assert len(data["blocks"]) == 7
    modules = [m for b in data["blocks"] for m in b["modules"]]
    assert len(modules) == 30
    lessons = [lesson for m in modules for lesson in m["lessons"]]
    # 30 modules, six of which carry a second lesson -> 36 in total.
    assert len(lessons) == 36
    assert [m["id"] for m in modules if len(m["lessons"]) == 2] == ["m03", "m08", "m09", "m17", "m19", "m24"]

    for m in modules:
        assert m["summary"]  # module theory blurb present
    for lesson in lessons:
        assert lesson["markdown"].strip()  # prose present
        assert "::exercise" not in lesson["markdown"]  # exercises stripped — theory only
    # A known lesson keeps its prose (incl. :::note callouts) but not its exercise directives.
    m12 = next(lesson for lesson in lessons if lesson["id"] == "m12-l1")
    assert "divergence" in m12["markdown"].lower() and ":::note" in m12["markdown"]

    # Spanish export is localized.
    es = (await content_client.get("/api/course/export?lang=es")).json()
    assert es["locale"] == "es"
    assert _module(es, "m16")["title"] == "Sentimiento de masas"

    # Download flag serves it as a file attachment, named for what is inside it.
    dl = await content_client.get("/api/course/export?lang=es&download=true")
    assert 'filename="tradeschool-course-es.json"' in dl.headers.get("content-disposition", "")


async def test_course_export_carries_both_languages_by_default(content_client: AsyncClient) -> None:
    """No `lang` means BOTH languages, not the reader's own."""
    await _auth(content_client)
    default = (await content_client.get("/api/course/export")).json()
    explicit = (await content_client.get("/api/course/export?lang=all")).json()
    assert default == explicit, "an absent lang and lang=all must be the same document"

    assert default["locales"] == ["en", "es"]
    assert "locale" not in default, "the bilingual document is discriminated by its `locales` key"
    modules = [m for b in default["blocks"] for m in b["modules"]]
    lessons = [lesson for m in modules for lesson in m["lessons"]]
    # The same walk of the manifest as the single-locale export, so the two cannot carry different
    # modules — for a document whose job is to be a faithful copy, that is the defect that matters.
    assert len(default["blocks"]) == 7 and len(modules) == 30 and len(lessons) == 36

    # Every localized field is paired, and each side matches the single-locale document exactly.
    for locale in ("en", "es"):
        single = (await content_client.get(f"/api/course/export?lang={locale}")).json()
        assert single["locale"] == locale
        assert [b["title"][locale] for b in default["blocks"]] == [b["title"] for b in single["blocks"]]
        single_modules = [m for b in single["blocks"] for m in b["modules"]]
        single_lessons = [x for m in single_modules for x in m["lessons"]]
        assert [x["markdown"][locale] for x in lessons] == [x["markdown"] for x in single_lessons]
        assert [m["summary"][locale] for m in modules] == [m["summary"] for m in single_modules]

    # ...and the two languages really are different text, not one copied into both slots.
    m30 = next(lesson for lesson in lessons if lesson["id"] == "m30-l1")
    assert m30["markdown"]["en"] != m30["markdown"]["es"]
    assert m30["title"]["es"] == "El dialecto SMC (order blocks, FVG, BOS)"

    dl = await content_client.get("/api/course/export?download=true")
    assert 'filename="tradeschool-course-all.json"' in dl.headers.get("content-disposition", "")


async def test_export_is_complete_against_the_manifest(content_client: AsyncClient) -> None:
    """Every manifest id, in canonical ORDER, in every document the export serves.

    Driven off `content/course.yaml` with no counts or id literals, so a hardcoded `== 30` cannot pass
    while the thirty-first module goes missing. Exercise ids are deliberately absent — this endpoint is
    theory — and that absence is asserted, so wanting them later announces itself here.
    """
    await _auth(content_client)
    manifest = load_registry(get_settings().content_dir).manifest
    want_blocks = [b.id for b in manifest.blocks]
    want_modules = [m.id for _, m in manifest.iter_modules()]
    want_lessons = [lesson.id for _, lesson in manifest.iter_lessons()]
    want_exercises = {ex.id for _, _, ex in manifest.iter_exercises()}
    assert want_blocks and want_modules and want_lessons and want_exercises  # the manifest is not empty

    for query in ("", "?lang=all", "?lang=en", "?lang=es"):
        doc = (await content_client.get(f"/api/course/export{query}")).json()
        where = f"/api/course/export{query or ' (no lang)'}"
        blocks = doc["blocks"]
        modules = [m for b in blocks for m in b["modules"]]
        lessons = [lesson for m in modules for lesson in m["lessons"]]

        assert [b["id"] for b in blocks] == want_blocks, f"{where}: block ids differ from the manifest"
        assert [m["id"] for m in modules] == want_modules, f"{where}: module ids differ from the manifest"
        assert [x["id"] for x in lessons] == want_lessons, f"{where}: lesson ids differ from the manifest"

        # A block can be present and hollow, so every leaf has to carry text in every locale it claims.
        locales = doc.get("locales") or [doc["locale"]]
        for lesson in lessons:
            body = lesson["markdown"]
            for locale in locales:
                text = body[locale] if isinstance(body, dict) else body
                assert text.strip(), f"{where}: {lesson['id']} has no prose in {locale}"
                assert "::exercise" not in text, f"{where}: {lesson['id']} kept an exercise directive"

        # ...and the fourth level stays out, which is what "theory only" means.
        serialized = json.dumps(doc, ensure_ascii=False)
        leaked = sorted(ex for ex in want_exercises if f'"{ex}"' in serialized)
        assert not leaked, f"{where}: exercise ids reached the theory export: {leaked}"


async def test_course_export_rejects_an_unknown_language(content_client: AsyncClient) -> None:
    await _auth(content_client)
    assert (await content_client.get("/api/course/export?lang=fr")).status_code == 422


async def test_course_tree_shape(content_client: AsyncClient) -> None:
    await _auth(content_client)
    course = (await content_client.get("/api/course")).json()
    assert [b["id"] for b in course["blocks"]] == [
        "block-a", "block-b", "block-c", "block-d", "block-e", "block-f", "block-g",
    ]

    # Root course identity for the header (localized; sourced from the manifest).
    assert course["course"]["id"] == "crypto-futures"
    assert course["course"]["title"] and course["course"]["description"]
    assert "started" in course

    m01 = _module(course, "m01")
    assert m01["hasContent"] is True and m01["lessonsTotal"] == 1
    # Reading and mastery are reported independently.
    assert m01["exercisesTotal"] == 2 and m01["exercisesPassed"] == 0
    # Phase 2 authored every module: m02 now has a lesson and its four exercises.
    m02 = _module(course, "m02")
    assert m02["hasContent"] is True and m02["lessonsTotal"] == 1 and m02["exercisesTotal"] == 4
    # m06 assumes m05, which the learner hasn't touched -> advisory notice.
    assert "m05" in _module(course, "m06")["unmetPrereqs"]


async def test_lesson_localized_and_has_exercises(content_client: AsyncClient) -> None:
    await _auth(content_client)
    en = (await content_client.get("/api/lessons/m01-l1?lang=en")).json()
    assert "crypto" in en["markdown"].lower()
    assert [e["id"] for e in en["exercises"]] == ["m01-ex-1", "m01-ex-2"]
    assert en["exercises"][0]["type"] == "quiz"

    es = (await content_client.get("/api/lessons/m01-l1?lang=es")).json()
    assert "cripto" in es["markdown"].lower()


async def test_missing_lesson_404(content_client: AsyncClient) -> None:
    await _auth(content_client)
    resp = await content_client.get("/api/lessons/does-not-exist")
    assert resp.status_code == 404
    assert resp.json()["code"] == "LESSON_NOT_FOUND"


async def test_complete_updates_progress_and_clears_prereq(content_client: AsyncClient) -> None:
    await _auth(content_client)
    # m02 assumes m01; before completing anything the notice is present.
    before = (await content_client.get("/api/course")).json()
    assert _module(before, "m02")["unmetPrereqs"] == ["m01"]

    done = await content_client.post("/api/lessons/m01-l1/complete")
    assert done.status_code == 200 and done.json()["completed"] is True

    after = (await content_client.get("/api/course")).json()
    assert _module(after, "m01")["lessonsCompleted"] == 1
    # Touching m01 clears the advisory prereq on m02.
    assert _module(after, "m02")["unmetPrereqs"] == []


async def test_progress_is_language_independent(content_client: AsyncClient) -> None:
    await _auth(content_client)
    await content_client.post("/api/lessons/m01-l1/complete")
    es_course = (await content_client.get("/api/course?lang=es")).json()
    assert _module(es_course, "m01")["lessonsCompleted"] == 1


async def test_complete_is_idempotent(content_client: AsyncClient) -> None:
    await _auth(content_client)
    assert (await content_client.post("/api/lessons/m01-l1/complete")).status_code == 200
    assert (await content_client.post("/api/lessons/m01-l1/complete")).status_code == 200
    course = (await content_client.get("/api/course")).json()
    assert _module(course, "m01")["lessonsCompleted"] == 1


async def test_module_detail_prereqs(content_client: AsyncClient) -> None:
    await _auth(content_client)
    detail = (await content_client.get("/api/modules/m06?lang=en")).json()
    assert detail["id"] == "m06"
    assert [a["id"] for a in detail["assumes"]] == ["m05"]
    assert [p["id"] for p in detail["unmetPrereqs"]] == ["m05"]


async def test_glossary_endpoint_serves_entries_at_its_real_path(
    content_client: AsyncClient,
) -> None:
    """Hits the ROUTE, not the registry.

    The first cut of the glossary page called `/api/content/glossary`, which 404s: the content router
    is mounted at `/api` with no prefix of its own. Nothing caught it because the backend tests called
    `glossary_entries()` directly and the frontend test mocked the client — so the URL itself was the
    one thing never exercised. This asserts the path.
    """
    assert (await content_client.get("/api/glossary")).status_code == 401
    # The mis-remembered path must stay a 404, so a future rename cannot quietly resurrect it.
    assert (await content_client.get("/api/content/glossary")).status_code == 404
    await _auth(content_client)

    response = await content_client.get("/api/glossary?lang=es")
    assert response.status_code == 200
    data = response.json()
    assert data["locale"] == "es"
    assert len(data["terms"]) > 0

    registry = load_registry(get_settings().content_dir)
    assert [t["term"] for t in data["terms"]] == [
        e["term"] for e in registry.glossary_entries("es")
    ]
    # The three shapes the page renders, all reachable over HTTP.
    assert any(t.get("aliasOf") for t in data["terms"])
    assert any(t.get("senses") for t in data["terms"])
    assert any(t.get("definition") for t in data["terms"])
