# SPDX-License-Identifier: AGPL-3.0-only
"""User and session-token tables.

TradeSchool identifies users by **username**, not email (self-hosted, no SMTP, no notifications).
The user table therefore does *not* inherit ``SQLAlchemyBaseUserTableUUID`` — that base hardcodes a
non-null unique ``email`` column. We spell the same columns out here, swapping ``email`` → ``username``.
Everything else (session tokens, password hashing, the ``current_user`` dependency) stays stock; see
``auth/manager.py`` for how the email-centric bits of fastapi-users are pointed at ``username``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import Boolean, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from tradeschool.db import Base


class User(Base):
    # Table name is "user" (fastapi-users default; the access-token FK targets it).
    __tablename__ = "user"

    id: Mapped[uuid.UUID] = mapped_column(GUID, primary_key=True, default=uuid.uuid4)
    # Sole identifier. Case-insensitive uniqueness + lookups are served by a functional UNIQUE index
    # on lower(username), created in the migration (expression indexes aren't modelled here).
    username: Mapped[str] = mapped_column(String(32), nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(1024), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    # Opaque, server-stored, revocable session token (database strategy). Table: "accesstoken".
    pass
