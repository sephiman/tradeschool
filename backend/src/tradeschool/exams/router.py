# SPDX-License-Identifier: AGPL-3.0-only
"""Exam endpoints. Only /submit and /review carry solutions; nothing reaches the client before then."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.auth.backend import current_active_user
from tradeschool.auth.models import User
from tradeschool.content.registry import CourseRegistry
from tradeschool.content.router import get_registry
from tradeschool.db import get_async_session
from tradeschool.deps import CourseId
from tradeschool.exams import service
from tradeschool.exams.schemas import (
    ExamAnswerRequest,
    ExamHistoryItem,
    ExamSessionOut,
    ExamStartRequest,
)

router = APIRouter(tags=["exams"], prefix="/exams")

LangQuery = Annotated[str | None, Query(pattern="^(en|es)$")]


def _locale(lang: str | None, user: User) -> str:
    if lang in ("en", "es"):
        return lang
    return user.locale if user.locale in ("en", "es") else "en"


@router.post("", response_model=ExamSessionOut, status_code=201)
async def start_exam(
    payload: ExamStartRequest,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> ExamSessionOut:
    view = await service.start_exam(
        session, registry, user.id, course, payload.scope, payload.blockId, _locale(lang, user)
    )
    return ExamSessionOut.build(view)


@router.get("/current", response_model=ExamSessionOut | None)
async def current_exam(
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> ExamSessionOut | None:
    view = await service.current_exam(session, registry, user.id, course, _locale(lang, user))
    return ExamSessionOut.build(view) if view else None


@router.get("", response_model=list[ExamHistoryItem])
async def exam_history(
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> list[ExamHistoryItem]:
    sessions = await service.exam_history(session, user.id, course)
    return [ExamHistoryItem.build(s, registry, _locale(lang, user)) for s in sessions]


@router.get("/{exam_id}", response_model=ExamSessionOut)
async def render_exam(
    exam_id: uuid.UUID,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> ExamSessionOut:
    view = await service.render_exam(session, registry, user.id, exam_id, course, _locale(lang, user))
    return ExamSessionOut.build(view)


@router.post("/{exam_id}/questions/{attempt_id}/answer", status_code=204)
async def answer_question(
    exam_id: uuid.UUID,
    attempt_id: uuid.UUID,
    payload: ExamAnswerRequest,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    course: CourseId,
) -> None:
    await service.answer_question(session, user.id, exam_id, course, attempt_id, payload.answer)


@router.post("/{exam_id}/submit", response_model=ExamSessionOut)
async def submit_exam(
    exam_id: uuid.UUID,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> ExamSessionOut:
    view = await service.submit_exam(session, registry, user.id, exam_id, course, _locale(lang, user))
    return ExamSessionOut.build(view)


@router.get("/{exam_id}/review", response_model=ExamSessionOut)
async def review_exam(
    exam_id: uuid.UUID,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    course: CourseId,
    lang: LangQuery = None,
) -> ExamSessionOut:
    view = await service.review_exam(session, registry, user.id, exam_id, course, _locale(lang, user))
    return ExamSessionOut.build(view)


@router.post("/{exam_id}/abandon", status_code=204)
async def abandon_exam(
    exam_id: uuid.UUID,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    course: CourseId,
) -> None:
    await service.abandon_exam(session, user.id, exam_id, course)
