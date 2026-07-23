# SPDX-License-Identifier: AGPL-3.0-only
"""Attempt lifecycle: open (generate a seeded scenario without the solution), answer (grade
server-side and reveal the instantiated solution), review (replay any past attempt from its seed).
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.content.registry import CourseRegistry
from tradeschool.errors import AppError
from tradeschool.exercises.base import GeneratedInstance, GradeResult, InvalidAnswerError
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.types import ExerciseType

_SEED_SPACE = 2**62


@dataclass
class OpenedAttempt:
    attempt: Attempt
    instance: GeneratedInstance
    exercise_type: ExerciseType


def _resolve(registry: CourseRegistry, exercise_id: str) -> tuple[ExerciseType, object]:
    config = registry.get_exercise_config(exercise_id)
    if config is None:
        # Distinguish "no such exercise in the course" from "declared but not yet playable".
        known = any(ex.id == exercise_id for _, _, ex in registry.manifest.iter_exercises())
        if known:
            raise AppError(
                "EXERCISE_NOT_AVAILABLE", f"Exercise {exercise_id!r} is not available.", status_code=409
            )
        raise AppError("EXERCISE_NOT_FOUND", f"No exercise {exercise_id!r}.", status_code=404)
    return config


async def open_attempt(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    exercise_id: str,
    locale: str,
) -> OpenedAttempt:
    exercise_type, config = _resolve(registry, exercise_id)
    generator = get_generator(exercise_type)
    seed = secrets.randbelow(_SEED_SPACE)
    instance = generator.generate(config, seed, locale)  # type: ignore[arg-type]

    # Abandoned rule (§3.4): opening a new attempt abandons any prior unanswered one for this exercise.
    await session.execute(
        update(Attempt)
        .where(
            Attempt.user_id == user_id,
            Attempt.exercise_id == exercise_id,
            Attempt.state == AttemptState.OPEN,
        )
        .values(state=AttemptState.ABANDONED)
    )
    attempt = Attempt(
        user_id=user_id,
        exercise_id=exercise_id,
        seed=seed,
        instance_snapshot={
            "type": exercise_type.value,
            "prompt": instance.prompt,
            "payload": instance.payload,
        },
        state=AttemptState.OPEN,
    )
    session.add(attempt)
    await session.commit()
    await session.refresh(attempt)
    return OpenedAttempt(attempt=attempt, instance=instance, exercise_type=exercise_type)


async def _load_owned(session: AsyncSession, user_id: uuid.UUID, attempt_id: uuid.UUID) -> Attempt:
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.user_id != user_id:
        raise AppError("ATTEMPT_NOT_FOUND", "No such attempt.", status_code=404)
    return attempt


async def submit_answer(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    answer: Mapping[str, object],
    locale: str,
) -> tuple[Attempt, GradeResult]:
    attempt = await _load_owned(session, user_id, attempt_id)
    if attempt.state != AttemptState.OPEN:
        raise AppError("ATTEMPT_ALREADY_RESOLVED", "This attempt is already resolved.", status_code=409)

    exercise_type, config = _resolve(registry, attempt.exercise_id)
    generator = get_generator(exercise_type)
    try:
        result = generator.grade(config, attempt.seed, answer, locale)  # type: ignore[arg-type]
    except InvalidAnswerError as exc:
        raise AppError("INVALID_ANSWER", str(exc), status_code=400) from exc

    attempt.given_answer = dict(answer)
    attempt.is_correct = result.correct
    attempt.state = AttemptState.ANSWERED
    attempt.answered_at = datetime.now(UTC)
    await session.commit()
    return attempt, result


@dataclass
class AttemptReview:
    attempt: Attempt
    exercise_type: ExerciseType
    instance: GeneratedInstance
    result: GradeResult | None


async def review_attempt(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    attempt_id: uuid.UUID,
    locale: str,
) -> AttemptReview:
    attempt = await _load_owned(session, user_id, attempt_id)
    exercise_type, config = _resolve(registry, attempt.exercise_id)
    generator = get_generator(exercise_type)
    # Replay the exact scenario from the seed, localized to the requested language.
    instance = generator.generate(config, attempt.seed, locale)  # type: ignore[arg-type]
    result: GradeResult | None = None
    if attempt.state == AttemptState.ANSWERED and attempt.given_answer is not None:
        result = generator.grade(config, attempt.seed, attempt.given_answer, locale)  # type: ignore[arg-type]
    return AttemptReview(attempt=attempt, exercise_type=exercise_type, instance=instance, result=result)


async def user_attempts(
    session: AsyncSession, user_id: uuid.UUID, exercise_id: str
) -> list[Attempt]:
    rows = await session.scalars(
        select(Attempt)
        .where(Attempt.user_id == user_id, Attempt.exercise_id == exercise_id)
        .order_by(Attempt.created_at.desc())
    )
    return list(rows.all())
