# SPDX-License-Identifier: AGPL-3.0-only
"""Exam request/response schemas. No solution fields are populated until a session is submitted."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from tradeschool.content.registry import CourseRegistry
from tradeschool.exams.models import ExamSession
from tradeschool.exams.service import ExamQuestionView, ExamView


class ExamStartRequest(BaseModel):
    scope: Literal["global", "block"]
    blockId: str | None = None


class ExamAnswerRequest(BaseModel):
    answer: dict[str, object]


class ExamQuestionOut(BaseModel):
    index: int
    attemptId: uuid.UUID
    moduleId: str
    moduleTitle: str
    blockId: str
    blockTitle: str
    exerciseId: str
    type: str
    prompt: str
    payload: dict[str, object]
    answered: bool
    givenAnswer: dict[str, object] | None
    # Reveal-only (populated on a submitted session's review):
    isCorrect: bool | None = None
    unanswered: bool | None = None
    correctAnswer: object | None = None
    solutionSteps: list[str] = []
    explanation: str | None = None

    @classmethod
    def build(cls, q: ExamQuestionView) -> ExamQuestionOut:
        return cls(
            index=q.index,
            attemptId=q.attempt_id,
            moduleId=q.module_id,
            moduleTitle=q.module_title,
            blockId=q.block_id,
            blockTitle=q.block_title,
            exerciseId=q.exercise_id,
            type=q.exercise_type.value,
            prompt=q.instance.prompt,
            payload=q.instance.payload,
            answered=q.answered,
            givenAnswer=q.given_answer,
            isCorrect=q.is_correct,
            unanswered=q.unanswered if q.result is not None else None,
            correctAnswer=q.result.correct_answer if q.result else None,
            solutionSteps=q.result.solution_steps if q.result else [],
            explanation=q.result.explanation if q.result else None,
        )


class ExamSessionOut(BaseModel):
    id: uuid.UUID
    scope: str
    blockId: str | None
    blockTitle: str | None
    status: str
    createdAt: datetime
    finishedAt: datetime | None
    result: dict[str, object] | None
    questions: list[ExamQuestionOut]

    @classmethod
    def build(cls, view: ExamView) -> ExamSessionOut:
        return cls(
            id=view.id,
            scope=view.scope,
            blockId=view.block_id,
            blockTitle=view.block_title,
            status=view.status,
            createdAt=view.created_at,
            finishedAt=view.finished_at,
            result=view.result,
            questions=[ExamQuestionOut.build(q) for q in view.questions],
        )


class ExamHistoryItem(BaseModel):
    id: uuid.UUID
    scope: str
    blockId: str | None
    blockTitle: str | None
    createdAt: datetime
    finishedAt: datetime | None
    score: float | None
    correct: int
    total: int

    @classmethod
    def build(cls, exam: ExamSession, registry: CourseRegistry, locale: str) -> ExamHistoryItem:
        rules = dict(exam.rules)
        result = rules.get("result") if isinstance(rules.get("result"), dict) else {}
        assert isinstance(result, dict)
        block_id = rules.get("blockId")
        block_id_str = block_id if isinstance(block_id, str) else None
        score = result.get("score")
        return cls(
            id=exam.id,
            scope=str(rules.get("scope", "global")),
            blockId=block_id_str,
            blockTitle=registry.block_title(block_id_str, locale) if block_id_str else None,
            createdAt=exam.created_at,
            finishedAt=exam.finished_at,
            score=score if isinstance(score, (int, float)) else None,
            correct=int(result.get("correct", 0) or 0),
            total=int(result.get("total", 0) or 0),
        )
