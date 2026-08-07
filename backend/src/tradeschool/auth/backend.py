# SPDX-License-Identifier: AGPL-3.0-only
"""Authentication backend: cookie transport + database (opaque token) strategy.

Reading a cookie uses the module-level transport (only the stable cookie name matters); WRITING one is
done in the router with the running app's settings, so Secure follows COOKIE_SECURE per deployment.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from fastapi_users import FastAPIUsers
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import AccessTokenDatabase, DatabaseStrategy
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from tradeschool.auth.manager import get_user_manager
from tradeschool.auth.models import AccessToken, User
from tradeschool.config import Settings, get_settings
from tradeschool.db import get_async_session

_settings = get_settings()

cookie_transport = CookieTransport(
    cookie_name=_settings.session_cookie_name,
    cookie_max_age=_settings.session_max_age,
    cookie_secure=_settings.cookie_secure,
    cookie_httponly=True,
    cookie_samesite="lax",
)


async def get_access_token_db(
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> AsyncGenerator[SQLAlchemyAccessTokenDatabase[AccessToken]]:
    yield SQLAlchemyAccessTokenDatabase(session, AccessToken)


# fastapi-users' generics are bound to its email-typed UserProtocol; our User keys on username
# instead (see auth/manager.py), so these library-boundary instantiations need a type-var waiver.
# Nothing here ever reads an email — the session backend is entirely user-id keyed.
SessionStrategy = DatabaseStrategy[User, uuid.UUID, AccessToken]  # type: ignore[type-var]


def get_database_strategy(
    access_token_db: Annotated[AccessTokenDatabase[AccessToken], Depends(get_access_token_db)],
) -> SessionStrategy:
    return DatabaseStrategy(access_token_db, lifetime_seconds=_settings.session_max_age)


auth_backend = AuthenticationBackend(  # type: ignore[type-var]
    name="db",
    transport=cookie_transport,
    get_strategy=get_database_strategy,
)

fastapi_users = FastAPIUsers[User, uuid.UUID](get_user_manager, [auth_backend])  # type: ignore[type-var]

current_active_user = fastapi_users.current_user(active=True)


def set_session_cookie(response: Response, token: str, settings: Settings) -> None:
    response.set_cookie(
        settings.session_cookie_name,
        token,
        max_age=settings.session_max_age,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        settings.session_cookie_name,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
