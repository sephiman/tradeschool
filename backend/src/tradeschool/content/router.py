# SPDX-License-Identifier: AGPL-3.0-only
"""Course navigation, lesson view and lesson completion. All content is localized to the
requested language (query `lang`, else the user's locale); progress is language-independent.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.auth.backend import current_active_user
from tradeschool.auth.models import User
from tradeschool.content.models import LessonCompletion
from tradeschool.content.registry import CourseRegistry
from tradeschool.content.schema import LOCALES
from tradeschool.db import get_async_session
from tradeschool.errors import AppError
from tradeschool.exercises.figures import build_figure

router = APIRouter(tags=["content"])

LangQuery = Annotated[str | None, Query(pattern="^(en|es)$")]


def get_registry(request: Request) -> CourseRegistry:
    registry: CourseRegistry = request.app.state.registry
    return registry


def _resolve_locale(lang: str | None, user: User) -> str:
    if lang in LOCALES:
        return lang
    if user.locale in LOCALES:
        return user.locale
    return "en"


async def _completed_lesson_ids(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    rows = await session.scalars(
        select(LessonCompletion.lesson_id).where(LessonCompletion.user_id == user_id)
    )
    return set(rows.all())


async def _has_any_attempt(session: AsyncSession, user_id: uuid.UUID) -> bool:
    """Whether the user has ever started an exercise — the 'has begun the course' signal."""
    row = await session.scalar(
        select(Attempt.exercise_id).where(Attempt.user_id == user_id).limit(1)
    )
    return row is not None


async def _passed_exercise_ids(session: AsyncSession, user_id: uuid.UUID) -> set[str]:
    """Exercises the user has answered correctly at least once — the mastery signal (≠ reading)."""
    rows = await session.scalars(
        select(Attempt.exercise_id)
        .where(
            Attempt.user_id == user_id,
            Attempt.state == AttemptState.ANSWERED,
            Attempt.is_correct.is_(True),
        )
        .distinct()
    )
    return set(rows.all())


class CompleteResponse(BaseModel):
    lessonId: str
    completed: bool


@router.get("/course")
async def get_course(
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> dict[str, object]:
    locale = _resolve_locale(lang, user)
    completed = await _completed_lesson_ids(session, user.id)
    passed = await _passed_exercise_ids(session, user.id)
    # `started` drives the course page's Continue CTA (hidden for a fresh account).
    started = bool(completed) or await _has_any_attempt(session, user.id)
    return {
        "locale": locale,
        "started": started,
        "course": registry.course_meta(locale),
        "blocks": registry.course_tree(locale, completed, passed),
    }


@router.get("/course/export")
async def export_course(
    user: Annotated[User, Depends(current_active_user)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
    download: Annotated[bool, Query()] = False,
) -> JSONResponse:
    """The whole course as a single JSON document — blocks → modules → lessons with the lesson prose
    only (exercises stripped) — for a logged-in user to read or archive. Localized via `lang` (else
    the user's locale). `?download=true` serves it as a file attachment."""
    locale = _resolve_locale(lang, user)
    data = registry.course_export(locale)
    headers = (
        {"Content-Disposition": f'attachment; filename="tradeschool-course-{locale}.json"'}
        if download
        else {}
    )
    return JSONResponse(content=data, headers=headers)


@router.get("/figures/{figure_id}")
async def get_figure(
    figure_id: str,
    request: Request,
    user: Annotated[User, Depends(current_active_user)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> dict[str, object]:
    """A lesson figure's rendered chart data + localized caption. Deterministic (frozen seed), so the
    built result is cached in-process per (figure, locale) — no per-request generation after the first."""
    locale = _resolve_locale(lang, user)
    spec = registry.figures.get(figure_id)
    if spec is None:
        raise AppError("FIGURE_NOT_FOUND", f"No figure {figure_id!r}.", status_code=404)
    if not hasattr(request.app.state, "figure_cache"):
        request.app.state.figure_cache = {}
    cache: dict[tuple[str, str], dict[str, object]] = request.app.state.figure_cache
    key = (figure_id, locale)
    if key not in cache:
        cache[key] = build_figure(spec, locale)
    return cache[key]


@router.get("/lessons/{lesson_id}")
async def get_lesson(
    lesson_id: str,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> dict[str, object]:
    locale = _resolve_locale(lang, user)
    completed = await _completed_lesson_ids(session, user.id)
    detail = registry.lesson_detail(lesson_id, locale, completed)
    if detail is None:
        raise AppError("LESSON_NOT_FOUND", f"No lesson {lesson_id!r}.", status_code=404)
    return detail


@router.post("/lessons/{lesson_id}/complete", response_model=CompleteResponse)
async def complete_lesson(
    lesson_id: str,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
) -> CompleteResponse:
    if registry.lesson_detail(lesson_id, "en", set()) is None:
        raise AppError("LESSON_NOT_FOUND", f"No lesson {lesson_id!r}.", status_code=404)
    await session.execute(
        pg_insert(LessonCompletion)
        .values(user_id=user.id, lesson_id=lesson_id)
        .on_conflict_do_nothing(index_elements=["user_id", "lesson_id"])
    )
    await session.commit()
    return CompleteResponse(lessonId=lesson_id, completed=True)


@router.get("/modules/{module_id}")
async def get_module(
    module_id: str,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> dict[str, object]:
    locale = _resolve_locale(lang, user)
    completed = await _completed_lesson_ids(session, user.id)
    detail = registry.module_detail(module_id, locale, completed)
    if detail is None:
        raise AppError("MODULE_NOT_FOUND", f"No module {module_id!r}.", status_code=404)
    return detail
