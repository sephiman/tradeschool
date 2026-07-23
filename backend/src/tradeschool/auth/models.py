# SPDX-License-Identifier: AGPL-3.0-only
"""User and session-token tables (fastapi-users SQLAlchemy bases + our columns)."""

from __future__ import annotations

from datetime import datetime

from fastapi_users_db_sqlalchemy import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from tradeschool.db import Base


class User(SQLAlchemyBaseUserTableUUID, Base):
    # Table name is "user" (fastapi-users default; the access-token FK targets it).
    locale: Mapped[str] = mapped_column(String(2), nullable=False, default="en", server_default="en")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AccessToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    # Opaque, server-stored, revocable session token (database strategy). Table: "accesstoken".
    pass
