# SPDX-License-Identifier: AGPL-3.0-only
"""Course-scoped URLs: the canonical scheme, the deprecated aliases, and an unknown slug.

The alias exists for clients we do not control. Ours use the scoped URLs — `test_no_internal_caller_
uses_an_alias` in the frontend suite is the other half of that promise.
"""

from __future__ import annotations

import hashlib
import json

import pytest
from httpx import AsyncClient

COURSE = "crypto-futures"
CREDS = {"username": "scoped", "password": "correcthorse"}

# (scoped path, deprecated alias) for every GET whose payload must not depend on which URL asked.
PAIRS = [
    (f"/api/courses/{COURSE}", "/api/course"),
    (f"/api/courses/{COURSE}/export?lang=es", "/api/course/export?lang=es"),
    (f"/api/courses/{COURSE}/export", "/api/course/export"),
    (f"/api/courses/{COURSE}/print/exercises?lang=es", "/api/course/print/exercises?lang=es"),
    (f"/api/courses/{COURSE}/glossary?lang=es", "/api/glossary?lang=es"),
    (f"/api/courses/{COURSE}/lessons/m01-l1", "/api/lessons/m01-l1"),
    (f"/api/courses/{COURSE}/modules/m01", "/api/modules/m01"),
    (f"/api/courses/{COURSE}/exams", "/api/exams"),
    (f"/api/courses/{COURSE}/exams/current", "/api/exams/current"),
    (f"/api/courses/{COURSE}/stats/me", "/api/stats/me"),
    (f"/api/courses/{COURSE}/stats/global", "/api/stats/global"),
]


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


def _digest(payload: object) -> str:
    return hashlib.md5(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@pytest.mark.parametrize(("scoped", "alias"), PAIRS)
async def test_scoped_and_alias_serve_the_same_payload(
    content_client: AsyncClient, scoped: str, alias: str
) -> None:
    await _auth(content_client)
    a = await content_client.get(scoped)
    b = await content_client.get(alias)
    assert a.status_code == 200, scoped
    assert b.status_code == 200, alias
    # Byte-identical: the alias serves directly, it does not redirect or re-render.
    assert _digest(a.json()) == _digest(b.json())


async def test_scoped_urls_require_auth_like_everything_else(content_client: AsyncClient) -> None:
    assert (await content_client.get(f"/api/courses/{COURSE}/glossary")).status_code == 401


async def test_unknown_course_slug_404s_cleanly(content_client: AsyncClient) -> None:
    await _auth(content_client)
    for path in ("", "/glossary", "/lessons/m01-l1", "/export", "/exams", "/stats/me"):
        response = await content_client.get(f"/api/courses/no-such-course{path}")
        assert response.status_code == 404, path
        assert response.json()["code"] == "COURSE_NOT_FOUND", path


async def test_an_unknown_slug_404s_before_the_resource_is_even_looked_up(
    content_client: AsyncClient,
) -> None:
    """A wrong course plus a wrong lesson is a course miss, not a lesson miss — the scope resolves first."""
    await _auth(content_client)
    response = await content_client.get("/api/courses/no-such-course/lessons/no-such-lesson")
    assert response.json()["code"] == "COURSE_NOT_FOUND"


async def test_aliases_carry_deprecation_headers_pointing_at_the_successor(
    content_client: AsyncClient,
) -> None:
    await _auth(content_client)
    response = await content_client.get("/api/glossary?lang=es")
    assert response.status_code == 200
    assert response.headers["deprecation"] == "true"
    assert response.headers["link"] == f'</api/courses/{COURSE}/glossary>; rel="successor-version"'

    # …and the export, whose handler returns a Response directly (the reason this is middleware).
    export = await content_client.get("/api/course/export?lang=es")
    assert export.headers["deprecation"] == "true"
    assert export.headers["link"] == f'</api/courses/{COURSE}/export>; rel="successor-version"'


async def test_the_canonical_url_is_not_marked_deprecated(content_client: AsyncClient) -> None:
    await _auth(content_client)
    response = await content_client.get(f"/api/courses/{COURSE}/glossary?lang=es")
    assert "deprecation" not in response.headers


async def test_only_scoped_urls_are_documented(content_client: AsyncClient) -> None:
    """The schema shows one canonical URL per endpoint; aliases are hidden so docs cannot teach them."""
    schema = (await content_client.get("/api/openapi.json")).json()
    course_owned = [
        p
        for p in schema["paths"]
        if not p.startswith(("/api/auth", "/api/health", "/api/version", "/api/dev"))
    ]
    assert course_owned, "no course-owned paths in the schema"
    assert all(p.startswith("/api/courses/{course}") for p in course_owned), course_owned
