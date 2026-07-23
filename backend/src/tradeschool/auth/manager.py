# SPDX-License-Identifier: AGPL-3.0-only
"""User manager: Argon2 hashing, password policy, registration hook."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, UUIDIDMixin, schemas
from fastapi_users.exceptions import InvalidPasswordException
from fastapi_users.password import PasswordHelper
from fastapi_users_db_sqlalchemy import SQLAlchemyUserDatabase
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.auth.models import User
from tradeschool.config import get_settings
from tradeschool.db import get_async_session

logger = logging.getLogger("tradeschool.auth")

# House requirement: Argon2 password hashing.
password_helper = PasswordHelper(PasswordHash((Argon2Hasher(),)))

MIN_PASSWORD_LENGTH = 8


async def get_user_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncGenerator[SQLAlchemyUserDatabase[User, uuid.UUID]]:
    yield SQLAlchemyUserDatabase(session, User)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    reset_password_token_secret = get_settings().auth_secret
    verification_token_secret = get_settings().auth_secret

    async def validate_password(self, password: str, user: schemas.UC | User) -> None:
        if len(password) < MIN_PASSWORD_LENGTH:
            raise InvalidPasswordException(
                f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
            )

    async def on_after_register(self, user: User, request: Request | None = None) -> None:
        logger.info("User registered: %s", user.id)


async def get_user_manager(
    user_db: Annotated[SQLAlchemyUserDatabase[User, uuid.UUID], Depends(get_user_db)],
) -> AsyncGenerator[UserManager]:
    yield UserManager(user_db, password_helper)
