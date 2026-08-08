# SPDX-License-Identifier: AGPL-3.0-only
"""exam sessions belong to a course

An exam session has always been in a course; the schema just could not say so, and its course was
only reachable by joining through its attempts' exercise ids. Course-scoped URLs need to answer
"does this exam belong to this course?" on every by-id route, so the column makes that a field
comparison rather than a join.

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-08-08 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COURSE_ID = "crypto-futures"


def upgrade() -> None:
    # Same shape as blocks/modules in e5f6a7b8c9d0: add nullable, backfill, then constrain. Every
    # existing exam session belongs to the one course that existed when it was taken.
    op.add_column("exam_sessions", sa.Column("course_id", sa.String(), nullable=True))
    op.execute(sa.text("UPDATE exam_sessions SET course_id = :id").bindparams(id=COURSE_ID))
    op.alter_column("exam_sessions", "course_id", nullable=False)
    op.create_index(
        op.f("ix_exam_sessions_course_id"), "exam_sessions", ["course_id"], unique=False
    )
    op.create_foreign_key(
        op.f("fk_exam_sessions_course_id_courses"),
        "exam_sessions",
        "courses",
        ["course_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("fk_exam_sessions_course_id_courses"), "exam_sessions", type_="foreignkey"
    )
    op.drop_index(op.f("ix_exam_sessions_course_id"), table_name="exam_sessions")
    op.drop_column("exam_sessions", "course_id")
