# SPDX-License-Identifier: AGPL-3.0-only
"""add pattern_chart to the exercise_type enum

Must land before the manifest can reconcile pattern_chart exercises.

Revision ID: c7d9e1f3a5b7
Revises: 1386dd39f51f
Create Date: 2026-07-22 20:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = 'c7d9e1f3a5b7'
down_revision: str | None = '1386dd39f51f'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # SQLAlchemy stores the enum MEMBER NAME for this native pg enum (QUIZ, CALCULATION, ...), so the
    # new value is the member name PATTERN_CHART. ADD VALUE is transaction-safe on PostgreSQL 12+ as
    # long as the value is not used in the same transaction (it isn't — the reconcile runs later).
    op.execute("ALTER TYPE exercise_type ADD VALUE IF NOT EXISTS 'PATTERN_CHART'")


def downgrade() -> None:
    # PostgreSQL cannot drop a value from an enum that columns may already hold; recreating the type
    # would require rewriting the exercises.type column and would fail if any pattern_chart rows
    # exist. The extra value is inert when unused, so downgrade is intentionally a no-op.
    pass
