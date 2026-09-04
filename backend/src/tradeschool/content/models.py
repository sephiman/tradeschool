# SPDX-License-Identifier: AGPL-3.0-only
"""Course skeleton tables (permanent keys, structure, order, active) and lesson completions.

Structural facts only; progress references these rows, never content (§8). Since 2026-08-10 the
`id` column of every skeleton table stores the entity's permanent KEY — equal to the display id at
creation, never renamed afterwards — so display ids can be renumbered without touching a row.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from tradeschool.db import Base
from tradeschool.exercises.types import ExerciseType


class SkeletonModel(Base):
    """Shared columns for every reconciled skeleton table: the permanent key and an active flag."""

    __abstract__ = True

    # The entity's permanent KEY (courses/blocks: identical to the display id, which never moves).
    id: Mapped[str] = mapped_column(String, primary_key=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")


class Course(SkeletonModel):
    """The root course a block/module tree belongs to; its localized labels live in the registry."""

    __tablename__ = "courses"

    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")


class Block(SkeletonModel):
    __tablename__ = "blocks"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class Module(SkeletonModel):
    __tablename__ = "modules"

    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False, index=True)
    block_id: Mapped[str] = mapped_column(ForeignKey("blocks.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # Advisory prerequisites (module ids). Informative, never a gate (§4.3).
    assumes: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default="[]")


class Lesson(SkeletonModel):
    __tablename__ = "lessons"

    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id"), nullable=False, index=True)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)


class Exercise(SkeletonModel):
    __tablename__ = "exercises"

    module_id: Mapped[str] = mapped_column(ForeignKey("modules.id"), nullable=False, index=True)
    lesson_id: Mapped[str | None] = mapped_column(ForeignKey("lessons.id"), nullable=True, index=True)
    type: Mapped[ExerciseType] = mapped_column(
        Enum(ExerciseType, name="exercise_type", native_enum=True), nullable=False
    )
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    # RETIRED 2026-09-04: `content_hash` — a hash of the generator config, meant to flag drift when an
    # exercise changed without getting a new id. Nothing ever wrote it and nothing ever read it, so
    # every row in every database has held NULL since the table was created; the drift it was going to
    # catch is caught instead by the frozen configs in `dist/contracts/generation-goldens/configs/`
    # and by the bundle's `contentFingerprint`, both of which cover the whole config rather than a
    # hash nobody computed. Same treatment as `calculation.tolerance`.
    #
    # The physical column is deliberately LEFT IN PLACE: dropping it is a one-line
    # `op.drop_column("exercises", "content_hash")` and this pass was scoped to additive migrations
    # only. It is nullable and unreferenced, so it costs a byte of catalogue and nothing else.
    # `tests/test_content_reconcile.py::RETIRED_EXERCISE_COLUMNS` keeps it from creeping back.


class LessonCompletion(Base):
    __tablename__ = "lesson_completions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("user.id", ondelete="cascade"), primary_key=True
    )
    lesson_id: Mapped[str] = mapped_column(
        ForeignKey("lessons.id", ondelete="cascade"), primary_key=True
    )
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
