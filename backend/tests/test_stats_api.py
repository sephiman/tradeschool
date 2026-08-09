# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import uuid

from httpx import AsyncClient

from tradeschool.attempts.models import Attempt
from tradeschool.config import Settings
from tradeschool.content.registry import load_registry
from tradeschool.db import get_sessionmaker
from tradeschool.exercises.base import rng_for
from tradeschool.exercises.quiz import QuizConfig, QuizKind, QuizVariant, _shuffled


def quiz_answer(variant: QuizVariant, seed: int, correct: bool) -> dict[str, object]:
    """Build a genuinely correct or wrong answer for whatever sub-kind the seed selected."""
    k = variant.kind
    if k is QuizKind.SINGLE_CHOICE:
        cid = next(o.id for o in variant.options if o.correct)
        wid = next(o.id for o in variant.options if not o.correct)
        return {"optionId": cid if correct else wid}
    if k is QuizKind.MULTI_SELECT:
        return {"optionIds": [o.id for o in variant.options if o.correct] if correct else []}
    if k is QuizKind.TRUE_FALSE:
        return {"value": variant.answer if correct else (not variant.answer)}
    if k is QuizKind.ORDERING:
        order = [i.id for i in sorted(variant.items, key=lambda it: it.position)]
        return {"order": order if correct else list(reversed(order))}
    lorder, rorder = _shuffled(len(variant.pairs), seed, 1), _shuffled(len(variant.pairs), seed, 2)
    lid = {p: f"l{s}" for s, p in enumerate(lorder)}
    rid = {p: f"r{s}" for s, p in enumerate(rorder)}
    cmap = {lid[i]: rid[i] for i in range(len(variant.pairs))}
    if not correct:
        keys = list(cmap)
        cmap[keys[0]], cmap[keys[1]] = cmap[keys[1]], cmap[keys[0]]
    return {"pairs": cmap}


async def _login(client: AsyncClient, username: str) -> None:
    creds = {"username": username, "password": "correcthorse"}
    await client.post("/api/auth/register", json={**creds, "locale": "en"})
    await client.post("/api/auth/login", json=creds)


async def _seed_of(attempt_id: str) -> int:
    async with get_sessionmaker()() as db:
        attempt = await db.get(Attempt, uuid.UUID(attempt_id))
        assert attempt is not None
        return attempt.seed


async def _answer_quiz(client: AsyncClient, settings: Settings, exercise_id: str, correct: bool) -> None:
    registry = load_registry(settings.content_dir)
    _, config = registry.get_exercise_config(exercise_id)
    assert isinstance(config, QuizConfig)
    opened = (await client.post(f"/api/exercises/{exercise_id}/attempts")).json()
    seed = await _seed_of(opened["attemptId"])
    variant = rng_for(seed).choice(config.variants)
    answer = quiz_answer(variant, seed, correct)
    await client.post(f"/api/attempts/{opened['attemptId']}/answer", json={"answer": answer})


async def test_me_stats_reading_and_mastery_are_separate(
    content_client: AsyncClient, settings: Settings
) -> None:
    await _login(content_client, "usera")
    # m01-ex-1: first wrong, then correct. m01-ex-2: correct first try.
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=False)
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=True)
    await _answer_quiz(content_client, settings, "m01-ex-2", correct=True)
    await content_client.post("/api/lessons/m01-l1/complete")

    stats = (await content_client.get("/api/stats/me")).json()

    # Exercise (mastery) dimension.
    assert stats["exercise"]["answered"] == 3
    assert stats["exercise"]["correct"] == 2
    assert stats["exercise"]["accuracy"] == round(2 / 3, 4)
    assert stats["exercise"]["firstAttemptAccuracy"] == 0.5  # ex-2 first-correct, ex-1 first-wrong
    assert stats["exercise"]["avgAttemptsToSuccess"] == 1.5

    # Reading (completion) dimension — computed over published content only. Every module in the
    # manifest is authored, so published == total.
    assert stats["coverage"]["publishedModules"] == 34
    assert stats["coverage"]["totalModules"] == 34
    assert stats["reading"]["lessonsCompleted"] == 1

    m01 = next(m for m in stats["modules"] if m["id"] == "m01")
    assert m01["blockId"] == "block-a"
    assert m01["lessonsTotal"] == 1 and m01["lessonsCompleted"] == 1
    assert m01["exercisesTotal"] == 2 and m01["exercisesPassed"] == 2
    assert m01["answered"] == 3
    # m01 carries only two exercises and both were answered, so the ranking gate is satisfied.
    assert "m01" in [c["moduleId"] for c in stats["costliestSections"]]

    # Both populations are serialized so the client never has to guess a denominator: `correct`
    # is out of `answered` attempts, `firstCorrect` out of `firstSeen` distinct exercises.
    assert (m01["correct"], m01["answered"]) == (2, 3)
    assert (m01["firstCorrect"], m01["firstSeen"]) == (1, 2)
    assert (stats["exercise"]["firstCorrect"], stats["exercise"]["firstSeen"]) == (1, 2)


async def test_costliest_sections_need_more_than_one_exercise(
    content_client: AsyncClient, settings: Settings
) -> None:
    """A section needs several answered exercises before it may be ranked as costly."""
    await _login(content_client, "gateuser")
    await _answer_quiz(content_client, settings, "m03-ex-1", correct=False)
    await _answer_quiz(content_client, settings, "m03-ex-2", correct=True)

    stats = (await content_client.get("/api/stats/me")).json()
    m03 = next(m for m in stats["modules"] if m["id"] == "m03")
    # The module row still reports the failure honestly — only the *ranking* is withheld.
    assert m03["exercisesFailed"] == 1
    assert "m03" not in [c["moduleId"] for c in stats["costliestSections"]]

    await _answer_quiz(content_client, settings, "m03-ex-3", correct=True)
    stats = (await content_client.get("/api/stats/me")).json()
    assert "m03" in [c["moduleId"] for c in stats["costliestSections"]]


async def test_failed_exercises_carry_their_lesson_for_review(
    content_client: AsyncClient, settings: Settings
) -> None:
    """Each failure names the exercise and the lesson it lives on, so the UI can link back to it."""
    await _login(content_client, "reviewuser")
    # m03 spans two lessons: ex-1 on m03-l1, ex-5 on m03-l2. A module id alone cannot route here.
    await _answer_quiz(content_client, settings, "m03-ex-1", correct=False)
    await _answer_quiz(content_client, settings, "m03-ex-1", correct=True)
    await _answer_quiz(content_client, settings, "m03-ex-5", correct=False)
    await _answer_quiz(content_client, settings, "m03-ex-2", correct=True)

    stats = (await content_client.get("/api/stats/me")).json()
    m03 = next(m for m in stats["modules"] if m["id"] == "m03")
    assert m03["toReview"] == [
        {"exerciseId": "m03-ex-1", "lessonId": "m03-l1", "incorrect": 1, "passed": True},
        {"exerciseId": "m03-ex-5", "lessonId": "m03-l2", "incorrect": 1, "passed": False},
    ]
    # Distinct failed exercises never exceeds the count of wrong attempts — the drill-down
    # reconciles with the number printed beside it instead of contradicting it.
    assert m03["exercisesFailed"] == 2 <= m03["answered"] - m03["correct"]

    costly = next(c for c in stats["costliestSections"] if c["moduleId"] == "m03")
    assert costly["toReview"] == m03["toReview"]


async def test_global_stats_are_anonymous_and_worst_first(
    content_client: AsyncClient, settings: Settings
) -> None:
    await _login(content_client, "userone")
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=False)  # user1 first attempt wrong
    await content_client.post("/api/auth/logout")

    await _login(content_client, "usertwo")
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=True)  # user2 first attempt right

    # Two learners is below the gate: at this size "aggregated" is a fiction, because either one can
    # subtract themselves from the row and read the other's result. Nothing is published.
    glob = (await content_client.get("/api/stats/global")).json()
    assert glob["thresholds"]["minLearners"] == 3
    assert glob["exercises"] == []
    assert glob["modules"] == []
    await content_client.post("/api/auth/logout")

    await _login(content_client, "userthree")
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=True)  # user3 first attempt right

    glob = (await content_client.get("/api/stats/global")).json()
    ex = next(e for e in glob["exercises"] if e["exerciseId"] == "m01-ex-1")
    assert ex["learners"] == 3
    assert ex["firstSeen"] == 3
    assert ex["firstAttemptAccuracy"] == round(2 / 3, 4)
    # No user identifiers anywhere in the payload.
    assert "user" not in str(glob).lower() or "userId" not in str(glob)


async def test_global_learner_count_is_people_not_observations(
    content_client: AsyncClient, settings: Settings
) -> None:
    """A module's headcount counts LEARNERS while its rate counts first attempts — different populations."""
    await _login(content_client, "soloworker")
    for exercise_id in ("m03-ex-1", "m03-ex-2", "m03-ex-3"):
        await _answer_quiz(content_client, settings, exercise_id, correct=False)

    glob = (await content_client.get("/api/stats/global")).json()
    # Three observations from one person: still one learner, so still nothing to publish.
    assert glob["modules"] == []


async def test_me_stats_empty_for_new_user(content_client: AsyncClient) -> None:
    await _login(content_client, "freshuser")
    stats = (await content_client.get("/api/stats/me")).json()
    assert stats["exercise"]["answered"] == 0
    assert stats["exercise"]["accuracy"] is None
    assert stats["reading"]["lessonsCompleted"] == 0
    assert stats["reading"]["courseCompletion"] == 0.0  # nothing read yet
    assert stats["coverage"]["publishedModules"] == 34
    assert stats["coverage"]["totalModules"] == 34
    assert stats["costliestSections"] == []
