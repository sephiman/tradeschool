# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.auth.models import User
from tradeschool.content.models import Block, Exercise, Lesson, LessonCompletion, Module
from tradeschool.content.schema import (
    LocalizedText,
    Manifest,
    ManifestBlock,
    ManifestCourse,
    ManifestExercise,
    ManifestLesson,
    ManifestModule,
)
from tradeschool.content.sync import reconcile
from tradeschool.exercises.types import ExerciseType


def _t(text: str) -> LocalizedText:
    return LocalizedText(en=text, es=text)


def _lesson(lesson_id: str, with_exercise: bool = False) -> ManifestLesson:
    ex = [ManifestExercise(id=f"{lesson_id}-ex", type=ExerciseType.QUIZ)] if with_exercise else []
    return ManifestLesson(id=lesson_id, title=_t(lesson_id), exercises=ex)


def _manifest(modules: list[ManifestModule]) -> Manifest:
    return Manifest(
        course=ManifestCourse(id="c1", title=_t("Course 1"), description=_t("A test course.")),
        blocks=[ManifestBlock(id="b1", title=_t("Block 1"), modules=modules)],
    )


async def test_reconcile_inserts_skeleton(session: AsyncSession) -> None:
    manifest = _manifest(
        [
            ManifestModule(id="mA", title=_t("A"), summary=_t("a"), lessons=[_lesson("lA", True)]),
            ManifestModule(id="mB", title=_t("B"), summary=_t("b"), assumes=["mA"]),
        ]
    )
    summary = await reconcile(manifest, session)
    assert summary.inserted == 1 + 1 + 2 + 1 + 1  # course + block + 2 modules + 1 lesson + 1 exercise

    block = await session.get(Block, "b1")
    assert block.active is True and block.course_id == "c1"
    assert (await session.get(Module, "mA")).course_id == "c1"
    m_a = await session.get(Module, "mA")
    m_b = await session.get(Module, "mB")
    assert m_a.order_index == 1 and m_b.order_index == 2
    assert m_b.assumes == ["mA"]
    ex = await session.get(Exercise, "lA-ex")
    assert ex.type == ExerciseType.QUIZ and ex.lesson_id == "lA" and ex.module_id == "mA"


async def test_reconcile_reorder_add_remove_preserves_progress(session: AsyncSession) -> None:
    # v1: two modules, each with a lesson; exercise on lB.
    v1 = _manifest(
        [
            ManifestModule(id="mA", title=_t("A"), summary=_t("a"), lessons=[_lesson("lA")]),
            ManifestModule(id="mB", title=_t("B"), summary=_t("b"), lessons=[_lesson("lB", True)]),
        ]
    )
    await reconcile(v1, session)

    # A learner completes lB.
    user = User(
        username="xlearner",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        locale="en",
    )
    session.add(user)
    await session.flush()
    session.add(LessonCompletion(user_id=user.id, lesson_id="lB"))
    await session.commit()

    # v2: mB removed; mA kept but moved after a new mC.
    v2 = _manifest(
        [
            ManifestModule(id="mC", title=_t("C"), summary=_t("c"), lessons=[_lesson("lC")]),
            ManifestModule(id="mA", title=_t("A"), summary=_t("a"), lessons=[_lesson("lA")]),
        ]
    )
    await reconcile(v2, session)

    m_c = await session.get(Module, "mC")
    m_a = await session.get(Module, "mA")
    m_b = await session.get(Module, "mB")
    assert m_c.active is True and m_c.order_index == 1
    assert m_a.active is True and m_a.order_index == 2
    # Removed content is inactivated, never deleted (§4.2).
    assert m_b.active is False
    assert (await session.get(Lesson, "lB")).active is False

    # Historical progress survives the reorganization.
    completions = (await session.scalars(select(LessonCompletion))).all()
    assert [c.lesson_id for c in completions] == ["lB"]


async def test_reconcile_moves_exercise_between_lessons_keeping_attempts(
    session: AsyncSession,
) -> None:
    """A re-homed exercise is UPDATED, not reinserted, so attempts keyed on its id survive."""
    ex = ManifestExercise(id="shared-ex", type=ExerciseType.QUIZ)
    module = ManifestModule(
        id="mA",
        title=_t("A"),
        summary=_t("a"),
        lessons=[
            ManifestLesson(id="lA", title=_t("lA"), exercises=[ex]),
            ManifestLesson(id="lB", title=_t("lB"), exercises=[]),
        ],
    )
    await reconcile(_manifest([module]), session)
    assert (await session.get(Exercise, "shared-ex")).lesson_id == "lA"

    user = User(
        username="ylearner",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        is_verified=False,
        locale="en",
    )
    session.add(user)
    await session.flush()
    session.add(
        Attempt(
            user_id=user.id,
            exercise_id="shared-ex",
            seed=7,
            instance_snapshot={"prompt": "p"},
            is_correct=True,
            state=AttemptState.ANSWERED,
        )
    )
    await session.commit()

    # The exercise moves to lB, and lands second behind a lesson-local newcomer.
    moved = ManifestModule(
        id="mA",
        title=_t("A"),
        summary=_t("a"),
        lessons=[
            ManifestLesson(id="lA", title=_t("lA"), exercises=[]),
            ManifestLesson(
                id="lB",
                title=_t("lB"),
                exercises=[ManifestExercise(id="lB-ex", type=ExerciseType.QUIZ), ex],
            ),
        ],
    )
    await reconcile(_manifest([moved]), session)

    row = await session.get(Exercise, "shared-ex")
    assert row.active is True  # re-homed, not removed
    assert row.lesson_id == "lB" and row.module_id == "mA"
    assert row.order_index == 2  # order is a plain attribute, so an out-of-sequence id is fine

    attempts = (await session.scalars(select(Attempt))).all()
    assert [(a.exercise_id, a.seed, a.is_correct) for a in attempts] == [("shared-ex", 7, True)]


async def test_reconcile_reactivates_returned_content(session: AsyncSession) -> None:
    v1 = _manifest([ManifestModule(id="mA", title=_t("A"), summary=_t("a"))])
    await reconcile(v1, session)
    await reconcile(_manifest([]), session)
    assert (await session.get(Module, "mA")).active is False
    # The same id reappearing flips it back to active.
    await reconcile(v1, session)
    assert (await session.get(Module, "mA")).active is True
