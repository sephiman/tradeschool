# SPDX-License-Identifier: AGPL-3.0-only
"""course entity

Introduces the root course table and links the existing block/module tree to it. All current
content belongs to the stable course id ``crypto-futures``; its blocks and modules are backfilled to
that id. Progress, attempts and stats tables are untouched.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-07-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str | None = "d4e5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COURSE_ID = "crypto-futures"


def upgrade() -> None:
    op.create_table(
        "courses",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("order_index", sa.Integer(), server_default="1", nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_courses")),
    )
    # The single existing course. Reconciliation keeps it in sync from here on.
    op.execute(sa.text("INSERT INTO courses (id, active, order_index) VALUES (:id, true, 1)").bindparams(id=COURSE_ID))

    for table in ("blocks", "modules"):
        op.add_column(table, sa.Column("course_id", sa.String(), nullable=True))
        op.execute(sa.text(f"UPDATE {table} SET course_id = :id").bindparams(id=COURSE_ID))
        op.alter_column(table, "course_id", nullable=False)
        op.create_index(op.f(f"ix_{table}_course_id"), table, ["course_id"], unique=False)
        op.create_foreign_key(
            op.f(f"fk_{table}_course_id_courses"), table, "courses", ["course_id"], ["id"]
        )


def downgrade() -> None:
    for table in ("modules", "blocks"):
        op.drop_constraint(op.f(f"fk_{table}_course_id_courses"), table, type_="foreignkey")
        op.drop_index(op.f(f"ix_{table}_course_id"), table_name=table)
        op.drop_column(table, "course_id")
    op.drop_table("courses")
