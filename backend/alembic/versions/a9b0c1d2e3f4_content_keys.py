# SPDX-License-Identifier: AGPL-3.0-only
"""Content columns store permanent KEYS, not display ids.

Revision ID: a9b0c1d2e3f4
Revises: f6a7b8c9d0e1
Create Date: 2026-08-10

The 2026-08-10 renumbering gave every module/lesson/exercise a permanent `key` — initialized to the
id each entity carried BEFORE the renumbering — and moved everything the DB stores onto it: the
skeleton tables' `id` column, `attempts.exercise_id`, `lesson_completions.lesson_id` and
`exam_sessions.course_id` (course ids double as keys). Every existing row already holds the old id,
which IS the key by construction, so the backfill is vacuous: this revision changes column
SEMANTICS and records them as column comments, and rewrites zero rows. It exists so the switch is a
dated, ordered fact of the schema history rather than a silent reinterpretation — and it is the
last migration a display reorder will ever need.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision: str = "a9b0c1d2e3f4"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | None = None
depends_on: str | None = None

_KEY = "the entity's permanent content key (= its display id at creation; never renamed)"
_COMMENTS: list[tuple[str, str, str]] = [
    ("courses", "id", _KEY),
    ("blocks", "id", _KEY),
    ("modules", "id", _KEY),
    ("lessons", "id", _KEY),
    ("exercises", "id", _KEY),
    ("attempts", "exercise_id", "permanent exercise key (see exercises.id)"),
    ("lesson_completions", "lesson_id", "permanent lesson key (see lessons.id)"),
    ("exam_sessions", "course_id", "permanent course key (see courses.id)"),
]


def upgrade() -> None:
    for table, column, comment in _COMMENTS:
        op.alter_column(table, column, existing_type=sa.String(), comment=comment)


def downgrade() -> None:
    for table, column, _comment in _COMMENTS:
        op.alter_column(table, column, existing_type=sa.String(), comment=None)
