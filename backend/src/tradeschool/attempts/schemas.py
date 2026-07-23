# SPDX-License-Identifier: AGPL-3.0-only
"""Attempt request/response schemas."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel

from tradeschool.attempts.models import Attempt, AttemptState
from tradeschool.attempts.service import AttemptReview, OpenedAttempt
from tradeschool.exercises.base import GradeResult


class AnswerRequest(BaseModel):
    answer: dict[str, object]


class AttemptInstance(BaseModel):
    """The statement as shown to the learner — never carries the solution (§3.1)."""

    attemptId: uuid.UUID
    exerciseId: str
    type: str
    prompt: str
    payload: dict[str, object]
    state: AttemptState

    @classmethod
    def from_opened(cls, opened: OpenedAttempt) -> AttemptInstance:
        return cls(
            attemptId=opened.attempt.id,
            exerciseId=opened.attempt.exercise_id,
            type=opened.exercise_type.value,
            prompt=opened.instance.prompt,
            payload=opened.instance.payload,
            state=opened.attempt.state,
        )


class GradeResponse(BaseModel):
    attemptId: uuid.UUID
    correct: bool
    correctAnswer: object
    solutionSteps: list[str]
    explanation: str | None

    @classmethod
    def build(cls, attempt: Attempt, result: GradeResult) -> GradeResponse:
        return cls(
            attemptId=attempt.id,
            correct=result.correct,
            correctAnswer=result.correct_answer,
            solutionSteps=result.solution_steps,
            explanation=result.explanation,
        )


class AttemptReviewResponse(BaseModel):
    attemptId: uuid.UUID
    exerciseId: str
    type: str
    prompt: str
    payload: dict[str, object]
    state: AttemptState
    givenAnswer: dict[str, object] | None
    isCorrect: bool | None
    correctAnswer: object | None
    solutionSteps: list[str]
    explanation: str | None
    createdAt: datetime
    answeredAt: datetime | None

    @classmethod
    def build(cls, review: AttemptReview) -> AttemptReviewResponse:
        a = review.attempt
        r = review.result
        return cls(
            attemptId=a.id,
            exerciseId=a.exercise_id,
            type=review.exercise_type.value,
            prompt=review.instance.prompt,
            payload=review.instance.payload,
            state=a.state,
            givenAnswer=a.given_answer,
            isCorrect=a.is_correct,
            correctAnswer=r.correct_answer if r else None,
            solutionSteps=r.solution_steps if r else [],
            explanation=r.explanation if r else None,
            createdAt=a.created_at,
            answeredAt=a.answered_at,
        )


class AttemptSummary(BaseModel):
    attemptId: uuid.UUID
    exerciseId: str
    state: AttemptState
    isCorrect: bool | None
    createdAt: datetime
    answeredAt: datetime | None

    @classmethod
    def build(cls, attempt: Attempt) -> AttemptSummary:
        return cls(
            attemptId=attempt.id,
            exerciseId=attempt.exercise_id,
            state=attempt.state,
            isCorrect=attempt.is_correct,
            createdAt=attempt.created_at,
            answeredAt=attempt.answered_at,
        )
