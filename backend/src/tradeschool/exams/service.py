# SPDX-License-Identifier: AGPL-3.0-only
"""Exam lifecycle: one exercise per module, no feedback until submission, then graded in bulk.

Exam attempts live in their own lane (``exam_session_id`` set) and never touch practice stats. The
practice generators are reused verbatim, so charts get the exercise-mode series, cut before resolution.
"""

from __future__ import annotations

import secrets
import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.content.registry import CourseRegistry
from tradeschool.errors import AppError
from tradeschool.exams.models import ExamSession
from tradeschool.exercises.base import GeneratedInstance, GradeResult
from tradeschool.exercises.registry import get_generator
from tradeschool.exercises.types import ExerciseType

_SEED_SPACE = 2**62

Scope = str  # "global" | "block"


# --- sentinel answers: let review reveal the correct answer + solution for an UNANSWERED question ---
# grade() computes the correct answer from the seed regardless of the input, but guards the input's
# shape first, so a structurally-valid (wrong) answer is enough to extract the solution.
def _sentinel_answer(exercise_type: ExerciseType, payload: Mapping[str, object]) -> dict[str, object]:
    if exercise_type is ExerciseType.PATTERN_CHART:
        return {"label": ""}
    if exercise_type in (ExerciseType.SYNTHETIC_CHART, ExerciseType.FIXTURE_CHART):
        return {"divergence": ""}
    if exercise_type is ExerciseType.QUIZ:
        kind = payload.get("kind")
        if kind == "multi_select":
            return {"optionIds": []}
        if kind == "true_false":
            return {"value": False}
        if kind == "ordering":
            return {"order": []}
        if kind == "matching":
            return {"pairs": {}}
        return {"optionId": ""}  # single_choice
    return {"optionId": ""}  # calculation


# --- view models handed to the router/schemas ---
@dataclass
class ExamQuestionView:
    index: int
    attempt_id: uuid.UUID
    module_id: str
    module_title: str
    block_id: str
    block_title: str
    exercise_id: str
    exercise_type: ExerciseType
    instance: GeneratedInstance
    given_answer: dict[str, object] | None
    answered: bool
    # Reveal-only (submitted session review):
    is_correct: bool | None = None
    unanswered: bool = False
    result: GradeResult | None = None


@dataclass
class ExamView:
    id: uuid.UUID
    scope: Scope
    block_id: str | None
    block_title: str | None
    status: str
    created_at: datetime
    finished_at: datetime | None
    questions: list[ExamQuestionView] = field(default_factory=list)
    result: dict[str, object] | None = None


def _ratio(num: int, den: int) -> float | None:
    return round(num / den, 4) if den else None


def _rules(exam: ExamSession) -> dict[str, object]:
    return dict(exam.rules)


# --- module selection ---
def _scope_modules(registry: CourseRegistry, scope: Scope, block_id: str | None) -> list[tuple[str, str]]:
    """(block_id, module_id) in canonical order, only modules with at least one playable exercise."""
    out: list[tuple[str, str]] = []
    for block, module in registry.manifest.iter_modules():
        if scope == "block" and block.id != block_id:
            continue
        if registry.playable_module_exercises(module.id):
            out.append((block.id, module.id))
    return out


async def _load_owned(
    session: AsyncSession, user_id: uuid.UUID, exam_id: uuid.UUID, course_id: str
) -> ExamSession:
    """The user's exam, IN this course. A course-scoped URL naming another course's exam is a miss,
    not a leak: it 404s exactly as an unknown id does, so the URL can never lie about what it holds."""
    exam = await session.get(ExamSession, exam_id)
    if exam is None or exam.user_id != user_id or exam.course_id != course_id:
        raise AppError("EXAM_NOT_FOUND", "No such exam session.", status_code=404)
    return exam


async def _open_sessions(
    session: AsyncSession, user_id: uuid.UUID, course_id: str
) -> list[ExamSession]:
    rows = await session.scalars(
        select(ExamSession)
        .where(
            ExamSession.user_id == user_id,
            ExamSession.course_id == course_id,
            ExamSession.finished_at.is_(None),
        )
        .order_by(ExamSession.created_at.desc())
    )
    return [s for s in rows.all() if s.rules.get("status") == "open"]


async def _attempts_of(session: AsyncSession, exam_id: uuid.UUID) -> list[Attempt]:
    """Ordered by id so the fallback path below is deterministic. The database has no inherent row
    order, and an unordered fetch made two renders of one exam disagree wherever the sort key tied."""
    rows = await session.scalars(
        select(Attempt).where(Attempt.exam_session_id == exam_id).order_by(Attempt.id)
    )
    return list(rows.all())


async def _abandon(session: AsyncSession, exam: ExamSession) -> None:
    exam.finished_at = datetime.now(UTC)
    exam.rules = {**exam.rules, "status": "abandoned"}
    await session.execute(
        update(Attempt).where(Attempt.exam_session_id == exam.id).values(state=AttemptState.ABANDONED)
    )


def _canonical_order(registry: CourseRegistry) -> dict[str, int]:
    return {module.id: i for i, (_, module) in enumerate(registry.manifest.iter_modules())}


#: Where a session's frozen question order lives, inside the `rules` JSONB it already has. A list of
#: exercise KEYS, in the order the exam was assembled — one per module, so the keys are unique within
#: a session.
QUESTION_ORDER = "questionOrder"


def _frozen_order(exam: ExamSession) -> dict[str, int] | None:
    """The order this exam was assembled in, or `None` for a session written before it was frozen."""
    order = exam.rules.get(QUESTION_ORDER)
    if not isinstance(order, list) or not order:
        return None
    return {str(key): index for index, key in enumerate(order)}


def _result_for_view(registry: CourseRegistry, result: dict[str, object]) -> dict[str, object]:
    """A stored result blob speaks keys (`moduleId`); the view speaks display ids."""
    out = dict(result)
    modules = result.get("modules")
    if isinstance(modules, list):
        out["modules"] = [
            {**m, "moduleId": registry.module_id_for_key(str(m.get("moduleId"))) or m.get("moduleId")}
            if isinstance(m, dict)
            else m
            for m in modules
        ]
    return out


def _build_view(
    session_obj: ExamSession,
    registry: CourseRegistry,
    attempts: list[Attempt],
    locale: str,
    reveal: bool,
) -> ExamView:
    def display_id(a: Attempt) -> str:
        return registry.exercise_id_for_key(a.exercise_id) or a.exercise_id

    # The order is FROZEN at assembly and read back here, rather than re-derived from today's manifest.
    # Re-deriving made an exam disagree with itself: the sort ran over the CURRENT module order, so a
    # display renumbering — which this repo supports on purpose, keys being permanent and ids not —
    # reordered the questions of an exam already sitting in review, and the `index` the UI paginates
    # by moved under it. Attempts store the permanent key, so the frozen list survives a renumbering.
    frozen = _frozen_order(session_obj)
    if frozen is not None:
        def sort_key(a: Attempt) -> int:
            return frozen.get(a.exercise_id, len(frozen))
    else:
        # Sessions assembled before the order was frozen. Same derivation as before, and `_attempts_of`
        # now orders by id so the ties this produces resolve the same way on every render.
        canonical = _canonical_order(registry)

        def sort_key(a: Attempt) -> int:
            loc = registry.exercise_location(display_id(a))
            return canonical.get(loc[1], 10_000) if loc else 10_000

    rules = _rules(session_obj)
    scope = str(rules.get("scope", "global"))
    block_id = rules.get("blockId")
    block_id_str = str(block_id) if isinstance(block_id, str) else None
    questions: list[ExamQuestionView] = []
    for index, attempt in enumerate(sorted(attempts, key=sort_key)):
        exercise_id = display_id(attempt)
        loc = registry.exercise_location(exercise_id)
        b_id, m_id = loc if loc else ("", "")
        config = registry.get_exercise_config(exercise_id)
        if config is None:
            continue  # exercise deactivated since the exam ran — skip defensively
        exercise_type, cfg = config
        generator = get_generator(exercise_type)
        instance = generator.generate(cfg, attempt.seed, locale)
        answered = attempt.given_answer is not None
        q = ExamQuestionView(
            index=index,
            attempt_id=attempt.id,
            module_id=m_id,
            module_title=registry.module_title(m_id, locale) or m_id,
            block_id=b_id,
            block_title=registry.block_title(b_id, locale) or b_id,
            exercise_id=exercise_id,
            exercise_type=exercise_type,
            instance=instance,
            given_answer=attempt.given_answer,
            answered=answered,
        )
        if reveal:
            sentinel = _sentinel_answer(exercise_type, instance.payload)
            reveal_answer = attempt.given_answer if attempt.given_answer is not None else sentinel
            try:
                q.result = generator.grade(cfg, attempt.seed, reveal_answer, locale)
            except Exception:
                # A malformed stored answer can't be graded; still reveal the correct answer + solution.
                q.result = generator.grade(cfg, attempt.seed, sentinel, locale)
            q.unanswered = not answered
            q.is_correct = bool(attempt.is_correct) and answered
        questions.append(q)

    block_title = registry.block_title(block_id_str, locale) if block_id_str else None
    result = rules.get("result")
    return ExamView(
        id=session_obj.id,
        scope=scope,
        block_id=block_id_str,
        block_title=block_title,
        status=str(rules.get("status", "open")),
        created_at=session_obj.created_at,
        finished_at=session_obj.finished_at,
        questions=questions,
        result=_result_for_view(registry, result) if isinstance(result, dict) else None,
    )


# --- lifecycle ---
async def start_exam(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    course_id: str,
    scope: Scope,
    block_id: str | None,
    locale: str,
) -> ExamView:
    if scope not in ("global", "block"):
        raise AppError("EXAM_BAD_SCOPE", f"Unknown exam scope {scope!r}.", status_code=400)
    if scope == "block":
        if block_id is None or not any(b.id == block_id for b in registry.manifest.blocks):
            raise AppError("EXAM_BAD_SCOPE", f"Unknown block {block_id!r}.", status_code=400)
    else:
        block_id = None

    modules = _scope_modules(registry, scope, block_id)
    if not modules:
        raise AppError("EXAM_EMPTY", "No playable modules for this exam scope.", status_code=409)

    # Starting a new exam of the same scope closes any open one of that scope.
    for existing in await _open_sessions(session, user_id, course_id):
        if existing.rules.get("scope") == scope and existing.rules.get("blockId") == block_id:
            await _abandon(session, existing)

    exam = ExamSession(
        user_id=user_id,
        course_id=course_id,
        rules={"scope": scope, "blockId": block_id, "status": "open"},
    )
    session.add(exam)
    await session.flush()  # assign exam.id for the attempt FK

    question_keys: list[str] = []
    for _b_id, module_id in modules:
        exercise_id = secrets.choice(registry.playable_module_exercises(module_id))
        config = registry.get_exercise_config(exercise_id)
        assert config is not None  # playable set guarantees it
        exercise_type, cfg = config
        generator = get_generator(exercise_type)
        seed = secrets.randbelow(_SEED_SPACE)
        instance = generator.generate(cfg, seed, locale)
        exercise_key = registry.exercise_key(exercise_id)
        question_keys.append(exercise_key)
        session.add(
            Attempt(
                user_id=user_id,
                exercise_id=exercise_key,  # rows store the permanent key
                seed=seed,
                instance_snapshot={
                    "type": exercise_type.value,
                    "prompt": instance.prompt,
                    "payload": instance.payload,
                },
                state=AttemptState.OPEN,
                exam_session_id=exam.id,
            )
        )
    # `modules` is in canonical order, so this IS the order the exam was assembled in — recorded now
    # rather than re-derived at every render. Additive: it goes in the `rules` JSONB the session
    # already has, so no schema migration, and a session written before this reads as `None`.
    exam.rules = {**exam.rules, QUESTION_ORDER: question_keys}
    await session.commit()
    return _build_view(exam, registry, await _attempts_of(session, exam.id), locale, reveal=False)


async def open_exams(
    session: AsyncSession, registry: CourseRegistry, user_id: uuid.UUID, course_id: str, locale: str
) -> list[ExamView]:
    """EVERY open sitting, newest first — not just the most recent one.

    `start_exam` only closes an open session of the SAME scope, so starting a block exam while a
    global one is unfinished leaves two open at once. The old `current_exam` returned
    `open_sessions[0]`, which meant the older sitting stayed open forever with no route in the UI that
    could reach it: the learner's half-finished exam was still consuming its questions and could
    neither be resumed nor abandoned.

    Listing them is preferred over the other available fix — closing the others when a new exam
    starts — because that one silently destroys work the learner never asked to discard, and the
    moment it would happen (starting an exam of a different scope) is not a moment they are thinking
    about the other one. The Android app already lists every open sitting; this is the web following.
    """
    return [
        _build_view(exam, registry, await _attempts_of(session, exam.id), locale, reveal=False)
        for exam in await _open_sessions(session, user_id, course_id)
    ]


async def render_exam(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    exam_id: uuid.UUID,
    course_id: str,
    locale: str,
) -> ExamView:
    exam = await _load_owned(session, user_id, exam_id, course_id)
    if exam.rules.get("status") != "open":
        raise AppError("EXAM_NOT_OPEN", "This exam is not in progress.", status_code=409)
    return _build_view(exam, registry, await _attempts_of(session, exam.id), locale, reveal=False)


async def answer_question(
    session: AsyncSession,
    user_id: uuid.UUID,
    exam_id: uuid.UUID,
    course_id: str,
    attempt_id: uuid.UUID,
    answer: Mapping[str, object],
) -> None:
    """Store (or replace) an answer. No grading, no reveal — feedback comes only at submission."""
    exam = await _load_owned(session, user_id, exam_id, course_id)
    if exam.rules.get("status") != "open":
        raise AppError("EXAM_NOT_OPEN", "This exam is not in progress.", status_code=409)
    attempt = await session.get(Attempt, attempt_id)
    if attempt is None or attempt.exam_session_id != exam_id:
        raise AppError("EXAM_QUESTION_NOT_FOUND", "No such question in this exam.", status_code=404)
    attempt.given_answer = dict(answer)
    await session.commit()


async def submit_exam(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    exam_id: uuid.UUID,
    course_id: str,
    locale: str,
) -> ExamView:
    exam = await _load_owned(session, user_id, exam_id, course_id)
    if exam.rules.get("status") != "open":
        raise AppError("EXAM_NOT_OPEN", "This exam is not in progress.", status_code=409)

    attempts = await _attempts_of(session, exam_id)
    now = datetime.now(UTC)
    per_module: list[dict[str, object]] = []
    order = _canonical_order(registry)
    correct_total = 0
    # Typed block accumulators (kept out of the object-valued dicts so the arithmetic stays clean).
    block_order: list[str] = []
    block_title: dict[str, str] = {}
    block_correct: dict[str, int] = {}
    block_total: dict[str, int] = {}

    def display_id(a: Attempt) -> str:
        return registry.exercise_id_for_key(a.exercise_id) or a.exercise_id

    for attempt in sorted(
        attempts, key=lambda a: order.get((registry.exercise_location(display_id(a)) or ("", ""))[1], 10_000)
    ):
        config = registry.get_exercise_config(display_id(attempt))
        answered = attempt.given_answer is not None
        is_correct = False
        if answered and config is not None:
            _etype, cfg = config
            generator = get_generator(config[0])
            try:
                graded = generator.grade(cfg, attempt.seed, attempt.given_answer or {}, locale)
                is_correct = graded.correct
            except Exception:
                is_correct = False
        # Unanswered (or ungradeable) → incorrect, but kept distinct in review via given_answer is None.
        attempt.is_correct = is_correct
        attempt.state = AttemptState.ANSWERED
        attempt.answered_at = now

        loc = registry.exercise_location(display_id(attempt))
        b_id, m_id = loc if loc else ("", "")
        per_module.append(
            {
                # Stored in the session's rules blob, so this is a KEY — display ids are resolved
                # at view time (`_result_for_view`), which is also what keeps pre-renumber exams true.
                "moduleId": registry.module_key(m_id) if m_id else m_id,
                "title": registry.module_title(m_id, locale) or m_id,
                "blockId": b_id,
                "correct": is_correct,
                "unanswered": not answered,
            }
        )
        if b_id not in block_total:
            block_order.append(b_id)
            block_title[b_id] = registry.block_title(b_id, locale) or b_id
            block_correct[b_id] = 0
            block_total[b_id] = 0
        block_total[b_id] += 1
        block_correct[b_id] += 1 if is_correct else 0
        correct_total += 1 if is_correct else 0

    total = len(per_module)
    blocks: list[dict[str, object]] = [
        {
            "blockId": b,
            "title": block_title[b],
            "correct": block_correct[b],
            "total": block_total[b],
            "score": _ratio(block_correct[b], block_total[b]),
        }
        for b in block_order
    ]
    result: dict[str, object] = {
        "score": _ratio(correct_total, total),
        "correct": correct_total,
        "total": total,
        "blocks": blocks,
        "modules": per_module,
    }
    exam.finished_at = now
    exam.rules = {**exam.rules, "status": "submitted", "result": result}
    await session.commit()
    return _build_view(exam, registry, await _attempts_of(session, exam_id), locale, reveal=True)


async def abandon_exam(
    session: AsyncSession, user_id: uuid.UUID, exam_id: uuid.UUID, course_id: str
) -> None:
    exam = await _load_owned(session, user_id, exam_id, course_id)
    if exam.rules.get("status") == "open":
        await _abandon(session, exam)
        await session.commit()


async def review_exam(
    session: AsyncSession,
    registry: CourseRegistry,
    user_id: uuid.UUID,
    exam_id: uuid.UUID,
    course_id: str,
    locale: str,
) -> ExamView:
    exam = await _load_owned(session, user_id, exam_id, course_id)
    if exam.rules.get("status") != "submitted":
        raise AppError("EXAM_NOT_SUBMITTED", "This exam has no results to review.", status_code=409)
    return _build_view(exam, registry, await _attempts_of(session, exam_id), locale, reveal=True)


async def exam_history(
    session: AsyncSession, user_id: uuid.UUID, course_id: str
) -> list[ExamSession]:
    """Submitted sessions, newest first (abandoned/open excluded — they count toward nothing)."""
    rows = await session.scalars(
        select(ExamSession)
        .where(
            ExamSession.user_id == user_id,
            ExamSession.course_id == course_id,
            ExamSession.finished_at.is_not(None),
        )
        .order_by(ExamSession.finished_at.desc())
    )
    return [s for s in rows.all() if s.rules.get("status") == "submitted"]
