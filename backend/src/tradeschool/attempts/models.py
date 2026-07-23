# SPDX-License-Identifier: AGPL-3.0-only
"""The attempts table — one row per opened attempt, fully reproducible from its seed."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tradeschool.db import Base


class AttemptState(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    ABANDONED = "abandoned"


class Attempt(Base):
    __tablename__ = "attempts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("user.id", ondelete="cascade"), index=True)
    exercise_id: Mapped[str] = mapped_column(ForeignKey("exercises.id"), index=True)
    # The seed fully determines the instantiated scenario (§3.2): any attempt is exactly replayable.
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # Cached public instance for fast history rendering (regenerable from the seed).
    instance_snapshot: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False)
    given_answer: Mapped[dict[str, object] | None] = mapped_column(JSONB, nullable=True)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    state: Mapped[AttemptState] = mapped_column(
        Enum(AttemptState, name="attempt_state"), nullable=False, default=AttemptState.OPEN
    )
    exam_session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("exam_sessions.id", ondelete="cascade"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
