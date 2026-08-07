# SPDX-License-Identifier: AGPL-3.0-only
"""Auth endpoints: thin wrappers over fastapi-users, so rate limiting and the error envelope apply."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.security import OAuth2PasswordRequestForm
from fastapi_users.exceptions import InvalidPasswordException, UserAlreadyExists
from starlette.responses import JSONResponse, Response

from tradeschool.auth.backend import (
    SessionStrategy,
    clear_session_cookie,
    current_active_user,
    get_database_strategy,
    set_session_cookie,
)
from tradeschool.auth.manager import UserManager, get_user_manager
from tradeschool.auth.models import User
from tradeschool.auth.schemas import LoginRequest, UserCreate, UserRead, UserUpdate
from tradeschool.config import Settings, get_settings
from tradeschool.deps import app_settings
from tradeschool.errors import AppError
from tradeschool.ratelimit import limiter

router = APIRouter(tags=["auth"])


@dataclass
class _Credentials:
    username: str
    password: str


def _register_limit() -> str:
    return get_settings().register_rate_limit


def _login_limit() -> str:
    return get_settings().login_rate_limit


@router.post("/register", response_model=UserRead, status_code=201)
@limiter.limit(_register_limit)
async def register(
    request: Request,
    payload: UserCreate,
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> UserRead:
    try:
        user = await user_manager.register(payload.username, payload.password, payload.locale)
    except UserAlreadyExists as exc:
        raise AppError(
            "USER_ALREADY_EXISTS", "That username is already taken.", status_code=400
        ) from exc
    except InvalidPasswordException as exc:
        raise AppError("INVALID_PASSWORD", str(exc.reason), status_code=400) from exc
    return UserRead.model_validate(user)


@router.post("/login")
@limiter.limit(_login_limit)
async def login(
    request: Request,
    payload: LoginRequest,
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
    strategy: Annotated[SessionStrategy, Depends(get_database_strategy)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> Response:
    creds = _Credentials(username=payload.username.strip(), password=payload.password)
    user = await user_manager.authenticate(cast(OAuth2PasswordRequestForm, creds))
    if user is None or not user.is_active:
        raise AppError("LOGIN_BAD_CREDENTIALS", "Invalid username or password.", status_code=400)

    token = await strategy.write_token(user)
    response = JSONResponse(UserRead.model_validate(user).model_dump(mode="json"))
    set_session_cookie(response, token, settings)
    await user_manager.on_after_login(user, request, response)
    return response


@router.post("/logout", status_code=204)
async def logout(
    request: Request,
    user: Annotated[User, Depends(current_active_user)],
    strategy: Annotated[SessionStrategy, Depends(get_database_strategy)],
    settings: Annotated[Settings, Depends(app_settings)],
) -> Response:
    token = request.cookies.get(settings.session_cookie_name)
    if token:
        await strategy.destroy_token(token, user)
    response = Response(status_code=204)
    clear_session_cookie(response, settings)
    return response


@router.get("/me", response_model=UserRead)
async def me(user: Annotated[User, Depends(current_active_user)]) -> User:
    return user


@router.patch("/me", response_model=UserRead)
async def update_me(
    payload: UserUpdate,
    user: Annotated[User, Depends(current_active_user)],
    user_manager: Annotated[UserManager, Depends(get_user_manager)],
) -> User:
    if payload.locale is not None:
        user = await user_manager.set_locale(user, payload.locale)
    return user
