# SPDX-License-Identifier: AGPL-3.0-only
"""The printed exercises and their answer key.

Checks the JOIN, not the text: every exercise re-graded from its own key, every quoted price indexed
back out of the published series. Driven off `content/course.yaml` with no id literals and no counts.
"""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from collections.abc import Mapping
from typing import Any

import pytest
from httpx import AsyncClient

from tradeschool.config import get_settings
from tradeschool.content import print_export
from tradeschool.content.print_export import (
    PrintExerciseError,
    build_print_exercises,
    print_number,
    print_seed,
)
from tradeschool.content.registry import CourseRegistry, load_registry
from tradeschool.content.schema import LOCALES
from tradeschool.exercises.base import GradeResult
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.reveal import RevealError, dummy_answer, reveal
from tradeschool.exercises.types import ExerciseType

CREDS = {"username": "printer", "password": "correcthorse"}

_registry: CourseRegistry | None = None
_built: dict[str, dict[str, Any]] = {}


def registry() -> CourseRegistry:
    global _registry
    if _registry is None:
        _registry = load_registry(get_settings().content_dir)
    return _registry


def built(locale: str) -> dict[str, Any]:
    """The print document for one locale, built once for the whole module."""
    if locale not in _built:
        _built[locale] = build_print_exercises(registry(), locale)
    return _built[locale]


def printed(locale: str) -> list[dict[str, Any]]:
    return [ex for lesson in built(locale)["lessons"] for ex in lesson["exercises"]]


def manifest_exercise_ids() -> list[str]:
    return [ex.id for _, _, ex in registry().manifest.iter_exercises()]


# --- completeness --------------------------------------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_print_export_is_complete_against_the_manifest(locale: str) -> None:
    """Every declared exercise is printed or excluded, in manifest ORDER — not just membership."""
    doc = built(locale)
    wanted = manifest_exercise_ids()
    assert wanted, "the manifest declares no exercises"

    excluded_ids = [e["id"] for e in doc["excluded"]]
    printed_ids = [ex["id"] for ex in printed(locale)]
    assert printed_ids == [eid for eid in wanted if eid not in set(excluded_ids)]
    # Nothing is both printed and excluded, and nothing is invented.
    assert set(printed_ids) | set(excluded_ids) == set(wanted)
    assert not set(printed_ids) & set(excluded_ids)

    # Lessons are a complete walk of the manifest too, so a lesson cannot go missing from the book by
    # having no exercises to print.
    assert [lesson["lessonId"] for lesson in doc["lessons"]] == [
        lesson.id for _, lesson in registry().manifest.iter_lessons()
    ]


@pytest.mark.parametrize("locale", LOCALES)
def test_every_printed_exercise_carries_exactly_one_answer(locale: str) -> None:
    """The bijection at its source: one answer per exercise, and no answer without an exercise."""
    for exercise in printed(locale):
        answer = exercise["answer"]
        assert isinstance(answer, dict) and answer.get("kind"), f"{exercise['id']} has no answer"
    numbers = [ex["number"] for ex in printed(locale)]
    # The answer key addresses exercises by number, so a duplicate number would make one of the two
    # unanswerable — the key would point at both.
    assert len(set(numbers)) == len(numbers)


def test_print_numbers_are_derived_from_ids_and_stay_unique() -> None:
    assert print_number("m11-ex-5") == "11.5"
    assert print_number("m01-ex-2") == "1.2"
    # An id outside the convention keeps its raw form rather than colliding with a derived number.
    assert print_number("bonus-quiz") == "bonus-quiz"
    ids = manifest_exercise_ids()
    assert len({print_number(eid) for eid in ids}) == len(ids)


# --- determinism ---------------------------------------------------------------------------------


def test_print_seed_is_stable_and_derived_from_the_id() -> None:
    """Frozen values, so a switch to a salted or reordered hash cannot pass quietly."""
    assert print_seed("m01-ex-1") == 3075867866203629967
    assert print_seed("m34-ex-4") == print_seed("m34-ex-4")
    assert print_seed("m01-ex-1") != print_seed("m01-ex-2")


def test_print_seed_is_the_same_in_a_fresh_process() -> None:
    """Needs a subprocess: `hash()` is salted per process, so in-process stability proves nothing."""
    code = "from tradeschool.content.print_export import print_seed; print(print_seed('m12-ex-1'))"
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert int(out.strip()) == print_seed("m12-ex-1")


@pytest.mark.parametrize("locale", LOCALES)
def test_two_builds_are_identical(locale: str) -> None:
    """Two generations of the same content version print the same instances and the same answers."""
    again = build_print_exercises(registry(), locale)
    assert json.dumps(again, sort_keys=True) == json.dumps(built(locale), sort_keys=True)


def _shape(payload: Mapping[str, Any]) -> dict[str, Any]:
    """A payload with the localized WORDS removed — the ids, order and numbers that ARE the instance."""
    ids = {
        key: [option["id"] for option in payload[key]]
        for key in ("options", "items", "lefts", "rights")
        if key in payload
    }
    panes = ("series", "rsi", "macd", "oi", "cvd", "overlays")
    numbers = {key: payload[key] for key in panes if key in payload}
    return {**ids, **numbers, "choices": payload.get("choices"), "kind": payload.get("kind")}


def _canonical(numeric_value: object, locale: str) -> object:
    """A printed number back to the value it states, so the two books can be compared as numbers.

    `numericValue` is a LABEL — the exact string the answer key prints, `35,00` in the ES book and
    `35.00` in the EN one. The two books still owe each other the same VALUE, which is what stripping
    each locale's separators checks. Spelled out here rather than imported: a guard that borrowed the
    formatter's own separator table would agree with it by construction.
    """
    if not isinstance(numeric_value, str):
        return numeric_value
    group, decimal = (".", ",") if locale == "es" else (",", ".")
    return numeric_value.replace(group, "").replace(decimal, ".")


def test_the_two_locales_print_the_same_instances() -> None:
    """Same seeds, same instance, different words — both books pose identical questions."""
    en = {ex["id"]: ex for ex in printed("en")}
    es = {ex["id"]: ex for ex in printed("es")}
    assert en.keys() == es.keys()
    for eid, exercise in en.items():
        assert exercise["seed"] == es[eid]["seed"]
        assert _shape(exercise["payload"]) == _shape(es[eid]["payload"]), f"{eid} differs per locale"
        # And the same answer: the key points at the same options and the same bars in both books.
        for key in ("kind", "optionIds", "order", "pairs", "value", "label"):
            assert exercise["answer"].get(key) == es[eid]["answer"].get(key), f"{eid}: {key}"
        # The one key that is a printed number rather than an id: same value, each book's separators.
        assert _canonical(exercise["answer"].get("numericValue"), "en") == _canonical(
            es[eid]["answer"].get("numericValue"), "es"
        ), f"{eid}: numericValue"
        assert [a["index"] for a in exercise["answer"].get("anchors", [])] == [
            a["index"] for a in es[eid]["answer"].get("anchors", [])
        ]


# --- the answer belongs to the printed instance --------------------------------------------------


@pytest.mark.parametrize("locale", LOCALES)
def test_every_answer_grades_as_correct_against_its_printed_seed(locale: str) -> None:
    """Each key re-submitted against its printed instance — the test the whole feature rests on."""
    for exercise in printed(locale):
        resolved = registry().get_exercise_config(exercise["id"])
        assert resolved is not None
        exercise_type, config = resolved
        generator = get_generator(exercise_type)
        verified = reveal(generator, config, exercise["seed"], locale, exercise["payload"])
        assert verified.result.correct, f"{exercise['id']}'s answer does not grade as correct"


@pytest.mark.parametrize("locale", LOCALES)
def test_chart_answers_are_priced_out_of_the_printed_series(locale: str) -> None:
    """Every price the key quotes is a value the printed chart actually plots, at the bar it names."""
    charts = [ex for ex in printed(locale) if ex["isChart"]]
    assert charts, "no chart exercises were printed"
    for exercise in charts:
        series = exercise["payload"]["series"]
        anchors = exercise["answer"]["anchors"]
        for anchor in anchors:
            index = anchor["index"]
            assert 0 <= index < len(series["close"])
            column = {"high": "high", "low": "low"}.get(anchor["kind"], "close")
            assert anchor["price"] == series[column][index], (
                f"{exercise['id']} quotes {anchor['price']} for bar {index}, "
                f"but the printed chart draws {series[column][index]}"
            )
            assert anchor["time"] == series["time"][index]
        for zone in exercise["answer"]["zones"]:
            # A zone is ground truth in price space; what is checkable is that it names prices the
            # printed chart reaches.
            assert zone["low"] <= max(series["high"]) and zone["high"] >= min(series["low"])
        # A chart exercise's answer is a label the reader could have chosen.
        assert exercise["answer"]["label"] in exercise["payload"]["choices"]


@pytest.mark.parametrize("locale", LOCALES)
def test_the_printed_payload_still_withholds_the_ground_truth(locale: str) -> None:
    """Printing an exercise does not turn its payload into a spoiler: markers and bands stay in the key."""
    for exercise in printed(locale):
        payload = exercise["payload"]
        assert "bands" not in payload, f"{exercise['id']} leaked its zones onto the question"
        assert "annotations" not in payload
        if exercise["type"] == "quiz":
            # A quiz option never carries its own correctness to the page.
            for option in payload.get("options", []):
                assert "correct" not in option


# --- exclusions ----------------------------------------------------------------------------------


def test_todays_course_prints_in_full() -> None:
    """Nothing in the course is currently unprintable. If this goes red, check `excluded` for the reason."""
    for locale in LOCALES:
        assert built(locale)["excluded"] == []


def test_an_unauthored_exercise_is_excluded_by_name_and_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Declared in the manifest, no config on disk: it cannot be printed, and it says so."""
    victim = manifest_exercise_ids()[0]
    stripped = CourseRegistry(
        manifest=registry().manifest,
        markdown=registry().markdown,
        exercise_configs={k: v for k, v in registry().exercise_configs.items() if k != victim},
        figures=registry().figures,
    )
    with caplog.at_level(logging.WARNING, logger="tradeschool.content"):
        doc = build_print_exercises(stripped, "en")

    excluded = doc["excluded"]
    assert [e["id"] for e in excluded] == [victim]
    assert "not authored" in excluded[0]["reason"]
    assert excluded[0]["lessonId"] == registry().exercise_lesson_id(victim)
    assert victim not in [ex["id"] for lesson in doc["lessons"] for ex in lesson["exercises"]]
    assert victim in caplog.text, "an excluded exercise was dropped without a word in the log"


def test_a_type_with_no_print_form_is_excluded_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """The rule that keeps a NEW exercise type from silently vanishing from the book."""
    monkeypatch.setattr(
        print_export,
        "ADAPTERS",
        {k: v for k, v in print_export.ADAPTERS.items() if k is not ExerciseType.CALCULATION},
    )
    doc = build_print_exercises(registry(), "en")
    excluded = doc["excluded"]
    calculations = [
        ex.id for _, _, ex in registry().manifest.iter_exercises() if ex.type is ExerciseType.CALCULATION
    ]
    assert [e["id"] for e in excluded] == calculations
    assert all("no print form" in e["reason"] for e in excluded)
    assert all(e["type"] == "calculation" for e in excluded)


def test_an_exercise_that_fails_to_build_is_excluded_with_what_it_threw(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_args: object, **_kwargs: object) -> dict[str, object]:
        raise PrintExerciseError("the chart would not build")

    monkeypatch.setitem(print_export.ADAPTERS, ExerciseType.PATTERN_CHART, boom)
    with caplog.at_level(logging.WARNING, logger="tradeschool.content"):
        doc = build_print_exercises(registry(), "en")
    assert doc["excluded"], "the failing type printed anyway"
    assert all(e["reason"] == "the chart would not build" for e in doc["excluded"])
    assert "the chart would not build" in caplog.text


# --- the reveal guard ----------------------------------------------------------------------------


def test_reveal_refuses_an_answer_the_grader_rejects() -> None:
    """A solution that does not grade as correct against its instance raises instead of publishing."""

    class Liar:
        def grade(
            self, _config: object, _seed: int, answer: Mapping[str, object], _locale: str
        ) -> GradeResult:
            # Reveals an option, then refuses it — the shape of a key that belongs to another seed.
            return GradeResult(correct=False, correct_answer={"optionId": "o1"})

    with pytest.raises(RevealError, match="does not grade as correct"):
        reveal(Liar(), None, 1, "en", {"options": [{"id": "o0"}]})  # type: ignore[arg-type]


@pytest.mark.parametrize("locale", LOCALES)
def test_dummy_answers_are_accepted_by_every_quiz_sub_kind(locale: str) -> None:
    """Every printed quiz kind accepts its dummy answer — `ordering`/`matching` reject a bare string."""
    kinds = set()
    for exercise in printed(locale):
        resolved = registry().get_exercise_config(exercise["id"])
        assert resolved is not None
        exercise_type, config = resolved
        generator = get_generator(exercise_type)
        # Raises InvalidAnswerError if the throwaway has the wrong shape for this kind.
        generator.grade(config, exercise["seed"], dummy_answer(exercise["payload"]), locale)
        kinds.add(exercise["answer"]["kind"])
    every_kind = {
        "single_choice", "true_false", "multi_select", "ordering", "matching", "calculation", "chart"
    }
    assert every_kind <= kinds


# --- the endpoint --------------------------------------------------------------------------------


async def _auth(client: AsyncClient) -> None:
    await client.post("/api/auth/register", json={**CREDS, "locale": "en"})
    await client.post("/api/auth/login", json=CREDS)


async def test_print_endpoint_requires_auth(content_client: AsyncClient) -> None:
    assert (await content_client.get("/api/course/print/exercises")).status_code == 401


async def test_print_endpoint_serves_the_built_document(content_client: AsyncClient) -> None:
    await _auth(content_client)
    for locale in LOCALES:
        response = await content_client.get(f"/api/course/print/exercises?lang={locale}")
        assert response.status_code == 200
        doc = response.json()
        assert doc["locale"] == locale
        assert json.dumps(doc, sort_keys=True) == json.dumps(built(locale), sort_keys=True)
        # Cached per locale: the second call is the same document, not a second generation.
        assert (await content_client.get(f"/api/course/print/exercises?lang={locale}")).json() == doc


async def test_the_theory_export_is_unchanged_by_all_this(content_client: AsyncClient) -> None:
    """The archive endpoint stays theory-only — the answer key is a separate door."""
    await _auth(content_client)
    doc = (await content_client.get("/api/course/export?lang=en")).json()
    text = json.dumps(doc)
    assert "::exercise" not in text
    assert not [eid for eid in manifest_exercise_ids() if eid in text]
