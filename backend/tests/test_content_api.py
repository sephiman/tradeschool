# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from typing import Any

from httpx import AsyncClient

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
    assert len(data["blocks"]) == 5
    modules = [m for b in data["blocks"] for m in b["modules"]]
    assert len(modules) == 24
    lessons = [lesson for m in modules for lesson in m["lessons"]]
    # 24 modules, six of which carry a second lesson -> 30 in total.
    assert len(lessons) == 30
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

    # Download flag serves it as a file attachment.
    dl = await content_client.get("/api/course/export?download=true")
    assert "attachment" in dl.headers.get("content-disposition", "")


async def test_course_tree_shape(content_client: AsyncClient) -> None:
    await _auth(content_client)
    course = (await content_client.get("/api/course")).json()
    assert [b["id"] for b in course["blocks"]] == ["block-a", "block-b", "block-c", "block-d", "block-e"]

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
