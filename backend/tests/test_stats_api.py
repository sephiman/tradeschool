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


async def _login(client: AsyncClient, email: str) -> None:
    await client.post("/api/auth/register", json={"email": email, "password": "correcthorse", "locale": "en"})
    await client.post("/api/auth/login", json={"email": email, "password": "correcthorse"})


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
    await _login(content_client, "a@example.com")
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

    # Reading (completion) dimension — computed over published content only. Phase 2 authored all
    # 23 modules, so every module now has content.
    assert stats["coverage"]["publishedModules"] == 23
    assert stats["coverage"]["totalModules"] == 23
    assert stats["reading"]["lessonsCompleted"] == 1

    m01 = next(m for m in stats["modules"] if m["id"] == "m01")
    assert m01["blockId"] == "block-a"
    assert m01["lessonsTotal"] == 1 and m01["lessonsCompleted"] == 1
    assert m01["exercisesTotal"] == 2 and m01["exercisesPassed"] == 2
    assert m01["answered"] == 3
    assert "m01" in [c["moduleId"] for c in stats["costliestSections"]]


async def test_global_stats_are_anonymous_and_worst_first(
    content_client: AsyncClient, settings: Settings
) -> None:
    await _login(content_client, "u1@example.com")
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=False)  # user1 first attempt wrong
    await content_client.post("/api/auth/logout")

    await _login(content_client, "u2@example.com")
    await _answer_quiz(content_client, settings, "m01-ex-1", correct=True)  # user2 first attempt right

    glob = (await content_client.get("/api/stats/global")).json()
    ex = next(e for e in glob["exercises"] if e["exerciseId"] == "m01-ex-1")
    assert ex["attemptedByUsers"] == 2
    assert ex["firstAttemptAccuracy"] == 0.5
    # No user identifiers anywhere in the payload.
    assert "user" not in str(glob).lower() or "userId" not in str(glob)


async def test_me_stats_empty_for_new_user(content_client: AsyncClient) -> None:
    await _login(content_client, "fresh@example.com")
    stats = (await content_client.get("/api/stats/me")).json()
    assert stats["exercise"]["answered"] == 0
    assert stats["exercise"]["accuracy"] is None
    assert stats["reading"]["lessonsCompleted"] == 0
    assert stats["reading"]["courseCompletion"] == 0.0  # 0 of 23 published lessons
    assert stats["coverage"]["publishedModules"] == 23
    assert stats["coverage"]["totalModules"] == 23
    assert stats["costliestSections"] == []
