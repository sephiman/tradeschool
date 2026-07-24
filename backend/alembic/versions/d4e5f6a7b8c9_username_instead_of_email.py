# SPDX-License-Identifier: AGPL-3.0-only
"""username instead of email

Switches user identity from email to username (self-hosted, no SMTP). Existing accounts get an
initial username derived from their email's local part (sanitized, collision-suffixed). The email
column is dropped, a case-insensitive UNIQUE index on lower(username) is added, and all session
tokens are cleared so everyone re-authenticates with their new username.

Revision ID: d4e5f6a7b8c9
Revises: c7d9e1f3a5b7
Create Date: 2026-07-24 00:00:00.000000
"""
from __future__ import annotations

import re
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: str | None = "c7d9e1f3a5b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _derive(email: str | None) -> str:
    """Initial username from an email's local part: lowercased, [a-z0-9_-] only, 3-32 chars."""
    local = (email or "").split("@", 1)[0].lower()
    base = re.sub(r"[^a-z0-9_-]", "", local) or "user"
    if len(base) < 3:
        base = (base + "user")[:32]
    return base[:32]


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column("user", sa.Column("username", sa.String(length=32), nullable=True))

    rows = bind.execute(sa.text('SELECT id, email FROM "user" ORDER BY created_at, id')).fetchall()
    taken: set[str] = set()
    for row in rows:
        base = _derive(row.email)
        name = base
        i = 2
        while name in taken:
            suffix = f"-{i}"
            name = f"{base[: 32 - len(suffix)]}{suffix}"
            i += 1
        taken.add(name)
        bind.execute(
            sa.text('UPDATE "user" SET username = :u WHERE id = :id'), {"u": name, "id": row.id}
        )

    op.alter_column("user", "username", nullable=False)
    # Case-insensitive uniqueness (and the identity lookup) live on this expression index.
    op.create_index("ix_user_username_lower", "user", [sa.text("lower(username)")], unique=True)

    op.drop_index(op.f("ix_user_email"), table_name="user")
    op.drop_column("user", "email")

    # Identity scheme changed — invalidate every session so users log in again by username.
    bind.execute(sa.text("DELETE FROM accesstoken"))


def downgrade() -> None:
    bind = op.get_bind()
    op.add_column("user", sa.Column("email", sa.String(length=320), nullable=True))
    # Original emails are unrecoverable; synthesize a unique, obviously-fake placeholder.
    bind.execute(
        sa.text("UPDATE \"user\" SET email = username || '@example.invalid' WHERE email IS NULL")
    )
    op.alter_column("user", "email", nullable=False)
    op.create_index(op.f("ix_user_email"), "user", ["email"], unique=True)
    op.drop_index("ix_user_username_lower", table_name="user")
    op.drop_column("user", "username")
