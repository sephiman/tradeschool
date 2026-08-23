# SPDX-License-Identifier: AGPL-3.0-only
"""The per-lesson reading-time estimate: what counts as prose, what a figure costs, one shared number.

Served in SECONDS and aggregated by the client, so no aggregate is computed from rounded minutes —
the frontend suite locks that half.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tradeschool.config import get_settings
from tradeschool.content.reading import (
    FIGURE_SECONDS,
    READING_WPM,
    estimate_seconds,
    figure_count,
    prose_text,
    prose_word_count,
)
from tradeschool.content.registry import load_registry

CREDS = {"username": "student", "password": "correcthorse"}

# A lesson with one of everything the stripper has to see through. The prose words are counted below,
# deliberately by hand, so the expected number is an assertion and not an echo of the implementation.
FIXTURE = """# Position sizing

Risk **one** percent of the account, never more.

::figure{id=fig-x1}

Use `Decimal` for money.

:::note{type=warning}
A stop is not optional.
:::

```python
size = risk / distance
```

- Size follows the stop.
- The stop follows structure.

::exercise{id=m01-ex-1}
"""
# # Position sizing                       -> 2   (heading text counts, the # does not)
# Risk **one** percent of the account,
#   never more.                           -> 8   (emphasis markers gone, words kept)
# ::figure{id=fig-x1}                     -> 0   (directive; paid for in FIGURE_SECONDS)
# Use `Decimal` for money.                -> 4   (inline code is a word in a sentence)
# A stop is not optional.                 -> 5   (callout prose counts; the ::: fences do not)
# ```python size = risk / distance ```    -> 0   (fenced code is not prose)
# - Size follows the stop.                -> 4   (list marker gone)
# - The stop follows structure.           -> 4
# ::exercise{id=m01-ex-1}                 -> 0   (exercises contribute nothing to a reading estimate)
FIXTURE_WORDS = 2 + 8 + 4 + 5 + 4 + 4


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


def _lessons(course: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        lesson for block in course["blocks"] for m in block["modules"] for lesson in m["lessons"]
    ]


def test_directives_and_markup_are_stripped_and_callout_prose_is_kept() -> None:
    """Headings, sentences, list items and callout text count; directives, fences and code do not."""
    text = prose_text(FIXTURE)
    # The directives and the fence syntax are gone...
    assert "::figure" not in text and "::exercise" not in text and ":::" not in text
    assert "```" not in text and "size = risk" not in text
    assert "**" not in text and "`" not in text and "#" not in text
    # ...and the prose, callout included, is not.
    assert "Position sizing" in text
    assert "one percent" in text, "emphasis markers dropped, the word they wrapped kept"
    assert "A stop is not optional." in text, "callout text is prose"
    assert "Decimal" in text, "inline code inside a sentence is a word"

    assert prose_word_count(FIXTURE) == FIXTURE_WORDS
    assert figure_count(FIXTURE) == 1
    # The estimate is that word count at the named rate, plus the figure — no hidden fudge factor.
    assert estimate_seconds(FIXTURE) == round(FIXTURE_WORDS / READING_WPM * 60) + FIGURE_SECONDS


def test_a_lesson_with_no_prose_at_all_still_costs_its_figures() -> None:
    """Zero words is zero seconds, but a lesson that is one chart is not free to read."""
    assert estimate_seconds("::exercise{id=m01-ex-1}\n") == 0
    assert estimate_seconds("::figure{id=fig-x1}\n") == FIGURE_SECONDS


def test_adding_a_figure_moves_the_estimate_by_exactly_figure_seconds() -> None:
    """The delta is exactly FIGURE_SECONDS, not "about 30" — the constant has to stay tunable."""
    before = estimate_seconds(FIXTURE)
    after = estimate_seconds(FIXTURE + "\n::figure{id=fig-x2}\n")
    assert figure_count(FIXTURE) + 1 == figure_count(FIXTURE + "\n::figure{id=fig-x2}\n")
    assert after - before == FIGURE_SECONDS


def test_estimates_are_per_locale_and_differ_between_es_and_en() -> None:
    """ES and EN estimate differently, and both nonzero — a locale at 0 would show no time at all."""
    registry = load_registry(get_settings().content_dir)
    en = registry.lesson_reading_seconds("m34-l1", "en")
    es = registry.lesson_reading_seconds("m34-l1", "es")
    assert en > 0 and es > 0
    assert en != es, "identical estimates would mean one locale's markdown was measured twice"
    # Every authored lesson is estimated in both languages, with no missing entries.
    for _, lesson in registry.manifest.iter_lessons():
        for locale in ("en", "es"):
            assert registry.lesson_reading_seconds(lesson.id, locale) > 0, f"{lesson.id}/{locale}"
    assert registry.lesson_reading_seconds("no-such-lesson", "en") == 0


def test_real_lessons_are_estimated_from_their_own_words_and_figures() -> None:
    """The registry's stored number is a pure function of that locale's markdown."""
    registry = load_registry(get_settings().content_dir)
    for locale in ("en", "es"):
        for _, lesson in registry.manifest.iter_lessons():
            body = registry.markdown[locale][lesson.id]
            assert registry.lesson_reading_seconds(lesson.id, locale) == estimate_seconds(body)


async def test_every_view_serves_the_same_per_lesson_seconds(content_client: AsyncClient) -> None:
    """Course, module and lesson payloads all carry `readingSeconds`, and they agree."""
    await _auth(content_client)

    course = (await content_client.get("/api/course?lang=en")).json()
    lessons = _lessons(course)
    assert lessons and all(lesson["readingSeconds"] > 0 for lesson in lessons)

    module = (await content_client.get("/api/modules/m08?lang=en")).json()
    missing = [x["id"] for x in module["lessons"] if "readingSeconds" not in x]
    assert missing == [], f"the module view serves lessons with no estimate: {missing}"
    from_course = {
        lesson["id"]: lesson["readingSeconds"]
        for lesson in lessons
        if lesson["id"].startswith("m08-")
    }
    assert {lesson["id"]: lesson["readingSeconds"] for lesson in module["lessons"]} == from_course
    assert len(from_course) == 2, "m08 carries two lessons — the case a module total is a real sum"

    for lesson_id, seconds in from_course.items():
        detail = (await content_client.get(f"/api/lessons/{lesson_id}?lang=en")).json()
        assert detail["readingSeconds"] == seconds

    # ...and the localized payload carries the localized estimate.
    es = (await content_client.get("/api/lessons/m34-l1?lang=es")).json()
    en = (await content_client.get("/api/lessons/m34-l1?lang=en")).json()
    assert es["readingSeconds"] > 0 and es["readingSeconds"] != en["readingSeconds"]


async def test_the_export_carries_no_reading_estimate(content_client: AsyncClient) -> None:
    """The export carries no reading estimate — a retunable calibration would silently age in an archive.

    Asserted over parsed KEYS, not a raw substring: a failing `not in` on megabytes of JSON takes
    pytest minutes to render.
    """
    await _auth(content_client)
    for query in ("", "?lang=en"):
        data = (await content_client.get(f"/api/course/export{query}")).json()
        modules = [m for block in data["blocks"] for m in block["modules"]]
        lessons = [lesson for m in modules for lesson in m["lessons"]]
        assert len(lessons) == 44
        offenders = sorted(
            {key for node in (*data["blocks"], *modules, *lessons) for key in node if "eading" in key}
        )
        assert offenders == [], f"reading-time keys leaked into the export: {offenders}"
