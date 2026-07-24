# SPDX-License-Identifier: AGPL-3.0-only
"""User manager: Argon2 hashing, password/username policy, username-keyed identity.

fastapi-users is email-centric. We keep its session/token backend, password hashing and the
timing-safe ``authenticate`` flow entirely stock, and point the one email-shaped hook it calls
(``get_by_email``) at our ``username`` column. Registration/locale updates go through small explicit
methods (``register`` / ``set_locale`` / ``set_password``) rather than the stock ``create``/``update``,
because those read an ``email`` field our schemas do not have.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin
from fastapi_users.exceptions import InvalidPasswordException, UserAlreadyExists
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.auth.models import User
from tradeschool.auth.schemas import Locale, normalize_username
from tradeschool.config import get_settings
from tradeschool.db import get_async_session

logger = logging.getLogger("tradeschool.auth")

# House requirement: Argon2 password hashing.
password_helper = PasswordHelper(PasswordHash((Argon2Hasher(),)))

MIN_PASSWORD_LENGTH = 8


class UserDatabase(SQLAlchemyUserDatabase[User, uuid.UUID]):  # type: ignore[type-var]
    """SQLAlchemy adapter keyed on ``username``. TradeSchool stores no email; ``get_by_email`` is the
    hook fastapi-users' ``authenticate``/``get_by_email`` call, so we alias it to the username lookup."""

    async def get_by_username(self, username: str) -> User | None:
        statement = select(User).where(func.lower(User.username) == func.lower(username))
        return await self._get_user(statement)

    async def get_by_email(self, email: str) -> User | None:
        # Identity lookup hook called by fastapi-users' authenticate(); aliased to username.
        return await self.get_by_username(email)


async def get_user_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncGenerator[UserDatabase]:
    yield UserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):  # type: ignore[type-var]
    reset_password_token_secret = get_settings().auth_secret
    verification_token_secret = get_settings().auth_secret

    async def validate_password(self, password: str, user: object = None) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidPasswordException(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        logger.info("User registered: %s", user.id)

    async def register(self, username: str, password: str, locale: Locale) -> User:
        """Create a user by username. Raises InvalidPasswordException / UserAlreadyExists / ValueError."""
        await self.validate_password(password)
        uname = normalize_username(username)  # ValueError -> 422 at the router
        db = self._username_db()
        if await db.get_by_username(uname) is not None:
            raise UserAlreadyExists()
        user = await db.create(
            {
                "username": uname,
                "hashed_password": self.password_helper.hash(password),
                "locale": locale,
                "is_active": True,
                "is_superuser": False,
                "is_verified": False,
            }
        )
        await self.on_after_register(user)
        return user

    async def set_locale(self, user: User, locale: str) -> User:
        return await self._username_db().update(user, {"locale": locale})

    async def set_password(self, user: User, new_password: str) -> User:
        await self.validate_password(new_password)
        return await self._username_db().update(
            user, {"hashed_password": self.password_helper.hash(new_password)}
        )

    def _username_db(self) -> UserDatabase:
        # user_db is always our UserDatabase (see get_user_manager); narrow it for the extra methods.
        assert isinstance(self.user_db, UserDatabase)
        return self.user_db


async def get_user_manager(
    user_db: Annotated[UserDatabase, Depends(get_user_db)],
) -> AsyncGenerator[UserManager]:
    yield UserManager(user_db, password_helper)
