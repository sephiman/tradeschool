# SPDX-License-Identifier: AGPL-3.0-only
"""Auth request/response schemas."""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi_users import schemas
from pydantic import BaseModel, ConfigDict, EmailStr

Locale = Literal["en", "es"]


class UserRead(schemas.BaseUser[uuid.UUID]):
    model_config = ConfigDict(from_attributes=True)
    locale: str


class UserCreate(schemas.BaseUserCreate):
    locale: Locale = "en"


class UserUpdate(schemas.BaseUserUpdate):
    locale: Locale | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
