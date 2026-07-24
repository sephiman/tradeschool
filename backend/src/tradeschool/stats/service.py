# SPDX-License-Identifier: AGPL-3.0-only
"""Derived statistics. Only *answered* attempts count; abandoned/open never affect accuracy (§3.4).
First-attempt accuracy is computed at the exercise level — the earliest answered attempt per
exercise — because that is the metric hardest to inflate by retrying."""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.content.models import LessonCompletion
from tradeschool.content.registry import CourseRegistry


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


@dataclass
class _ExerciseRoll:
    answered: int = 0
    correct: int = 0
    first_correct: bool | None = None  # correctness of the earliest answered attempt
    attempts_to_success: int | None = None  # answered attempts up to and incl. the first correct

    def add(self, is_correct: bool) -> None:
        self.answered += 1
        if is_correct:
            self.correct += 1
        if self.first_correct is None:
            self.first_correct = is_correct
        if self.attempts_to_success is None and is_correct:
            self.attempts_to_success = self.answered


async def _answered(session: AsyncSession, user_id: uuid.UUID | None) -> list[Attempt]:
    # Practice only: exam attempts (exam_session_id set) never touch practice statistics — first-attempt
    # accuracy, costliest sections and the global "where everyone struggles" all exclude them (§isolation).
    stmt = select(Attempt).where(
        Attempt.state == AttemptState.ANSWERED, Attempt.exam_session_id.is_(None)
    )
    if user_id is not None:
        stmt = stmt.where(Attempt.user_id == user_id)
    stmt = stmt.order_by(Attempt.created_at.asc(), Attempt.id.asc())
    return list((await session.scalars(stmt)).all())


def _roll_by_exercise(attempts: list[Attempt]) -> dict[str, _ExerciseRoll]:
    rolls: dict[str, _ExerciseRoll] = defaultdict(_ExerciseRoll)
    for a in attempts:
        rolls[a.exercise_id].add(bool(a.is_correct))
    return rolls


@dataclass
class _Agg:
    answered: int = 0
    correct: int = 0
    first_seen: int = 0
    first_correct: int = 0
    success_attempts: list[int] = field(default_factory=list)


def _avg(values: list[int]) -> float | None:
    return round(sum(values) / len(values), 2) if values else None


async def me_stats(
    session: AsyncSession, registry: CourseRegistry, user_id: uuid.UUID, locale: str
) -> dict[str, object]:
    rolls = _roll_by_exercise(await _answered(session, user_id))
    passed = {eid for eid, roll in rolls.items() if roll.correct > 0}

    completed_rows = await session.scalars(
        select(LessonCompletion.lesson_id).where(LessonCompletion.user_id == user_id)
    )
    completed_lessons = set(completed_rows.all())

    overall = _Agg()  # exercise stats across all published modules
    module_rows: list[dict[str, object]] = []
    costly_src: list[tuple[str, str | None, _Agg]] = []
    published_lessons = 0
    completed_published = 0
    published_modules = 0
    total_modules = 0

    for block, module in registry.manifest.iter_modules():
        total_modules += 1
        lesson_ids = registry.module_lesson_ids(module.id)
        if not lesson_ids:
            continue  # unpublished — excluded from coverage and reading (§ report on published only)
        published_modules += 1
        lessons_done = sum(1 for lid in lesson_ids if lid in completed_lessons)
        published_lessons += len(lesson_ids)
        completed_published += lessons_done

        exercise_ids = registry.module_exercise_ids(module.id)
        mod = _Agg()
        for eid in exercise_ids:
            roll = rolls.get(eid)
            if roll is None:
                continue
            for agg in (mod, overall):
                agg.answered += roll.answered
                agg.correct += roll.correct
                agg.first_seen += 1
                agg.first_correct += 1 if roll.first_correct else 0
                if roll.attempts_to_success is not None:
                    agg.success_attempts.append(roll.attempts_to_success)

        module_rows.append(
            {
                "id": module.id,
                "title": module.title.get(locale),
                "blockId": block.id,
                # Reading (completion) — kept separate from mastery, never merged into one score.
                "lessonsTotal": len(lesson_ids),
                "lessonsCompleted": lessons_done,
                # Mastery (exercises).
                "exercisesTotal": len(exercise_ids),
                "exercisesPassed": sum(1 for eid in exercise_ids if eid in passed),
                "answered": mod.answered,
                "accuracy": _ratio(mod.correct, mod.answered),
                "firstAttemptAccuracy": _ratio(mod.first_correct, mod.first_seen),
            }
        )
        if mod.answered - mod.correct > 0:
            costly_src.append((module.id, module.title.get(locale), mod))

    costly_src.sort(
        key=lambda t: (-(t[2].answered - t[2].correct), _ratio(t[2].first_correct, t[2].first_seen) or 0.0)
    )
    costliest = [
        {
            "moduleId": mid,
            "title": title,
            "incorrect": mod.answered - mod.correct,
            "answered": mod.answered,
            "firstAttemptAccuracy": _ratio(mod.first_correct, mod.first_seen),
        }
        for mid, title, mod in costly_src[:5]
    ]

    return {
        "coverage": {
            "publishedModules": published_modules,
            "totalModules": total_modules,
            "publishedLessons": published_lessons,
        },
        "reading": {
            "lessonsCompleted": completed_published,
            "lessonsTotal": published_lessons,
            "courseCompletion": _ratio(completed_published, published_lessons),
        },
        "exercise": {
            "answered": overall.answered,
            "correct": overall.correct,
            "accuracy": _ratio(overall.correct, overall.answered),
            "firstAttemptAccuracy": _ratio(overall.first_correct, overall.first_seen),
            "avgAttemptsToSuccess": _avg(overall.success_attempts),
        },
        "modules": module_rows,
        "costliestSections": costliest,
    }


async def global_stats(session: AsyncSession, registry: CourseRegistry, locale: str) -> dict[str, object]:
    attempts = await _answered(session, None)

    # earliest answered attempt per (user, exercise) — the first-attempt population.
    first_seen: dict[tuple[uuid.UUID, str], bool] = {}
    for a in attempts:
        key = (a.user_id, a.exercise_id)
        if key not in first_seen:
            first_seen[key] = bool(a.is_correct)

    by_exercise: dict[str, _Agg] = defaultdict(_Agg)
    by_module: dict[str, _Agg] = defaultdict(_Agg)
    for (_, exercise_id), correct in first_seen.items():
        loc = registry.exercise_location(exercise_id)
        if loc is None:
            continue
        _, module_id = loc
        for agg in (by_exercise[exercise_id], by_module[module_id]):
            agg.first_seen += 1
            agg.first_correct += 1 if correct else 0

    exercises = sorted(
        (
            {
                "exerciseId": exercise_id,
                "moduleId": (registry.exercise_location(exercise_id) or ("", ""))[1],
                "attemptedByUsers": agg.first_seen,
                "firstAttemptAccuracy": _ratio(agg.first_correct, agg.first_seen),
            }
            for exercise_id, agg in by_exercise.items()
        ),
        key=lambda d: (d["firstAttemptAccuracy"] if d["firstAttemptAccuracy"] is not None else 1.0),
    )
    module_rows = sorted(
        (
            {
                "moduleId": mid,
                "title": registry.module_title(mid, locale),
                "attemptedByUsers": agg.first_seen,
                "firstAttemptAccuracy": _ratio(agg.first_correct, agg.first_seen),
            }
            for mid, agg in by_module.items()
        ),
        key=lambda d: (d["firstAttemptAccuracy"] if d["firstAttemptAccuracy"] is not None else 1.0),
    )
    return {"exercises": exercises, "modules": module_rows}
