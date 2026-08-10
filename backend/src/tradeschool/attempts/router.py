# SPDX-License-Identifier: AGPL-3.0-only
"""Attempt endpoints (the core exercise flow, §3.1)."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.attempts import service
from tradeschool.attempts.schemas import (
    AnswerRequest,
    AttemptInstance,
    AttemptReviewResponse,
    AttemptSummary,
    GradeResponse,
)
from tradeschool.auth.backend import current_active_user
from tradeschool.auth.models import User
from tradeschool.content.registry import CourseRegistry
from tradeschool.content.router import get_registry
from tradeschool.db import get_async_session

router = APIRouter(tags=["attempts"])

LangQuery = Annotated[str | None, Query(pattern="^(en|es)$")]


def _resolve_locale(lang: str | None, user: User) -> str:
    if lang in ("en", "es"):
        return lang
    return user.locale if user.locale in ("en", "es") else "en"


@router.post("/exercises/{exercise_id}/attempts", response_model=AttemptInstance, status_code=201)
async def create_attempt(
    exercise_id: str,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> AttemptInstance:
    opened = await service.open_attempt(session, registry, user.id, exercise_id, _resolve_locale(lang, user))
    return AttemptInstance.from_opened(opened)


@router.post("/attempts/{attempt_id}/answer", response_model=GradeResponse)
async def answer_attempt(
    attempt_id: uuid.UUID,
    payload: AnswerRequest,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> GradeResponse:
    attempt, result = await service.submit_answer(
        session, registry, user.id, attempt_id, payload.answer, _resolve_locale(lang, user)
    )
    return GradeResponse.build(attempt, result)


@router.get("/attempts/{attempt_id}", response_model=AttemptReviewResponse)
async def review_attempt(
    attempt_id: uuid.UUID,
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
    lang: LangQuery = None,
) -> AttemptReviewResponse:
    review = await service.review_attempt(session, registry, user.id, attempt_id, _resolve_locale(lang, user))
    return AttemptReviewResponse.build(review)


@router.get("/attempts", response_model=list[AttemptSummary])
async def list_attempts(
    exercise_id: Annotated[str, Query()],
    user: Annotated[User, Depends(current_active_user)],
    session: Annotated[AsyncSession, Depends(get_async_session)],
    registry: Annotated[CourseRegistry, Depends(get_registry)],
) -> list[AttemptSummary]:
    attempts = await service.user_attempts(session, registry, user.id, exercise_id)
    return [AttemptSummary.build(a, exercise_id) for a in attempts]
