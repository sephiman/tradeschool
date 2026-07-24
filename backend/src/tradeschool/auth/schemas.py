# SPDX-License-Identifier: AGPL-3.0-only
"""Auth request/response schemas — username-based (no email anywhere)."""

from __future__ import annotations

import re
import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator

Locale = Literal["en", "es"]

USERNAME_MIN = 3
USERNAME_MAX = 32
# Letters, digits, hyphen and underscore. Normalized to lowercase for case-insensitive identity.
USERNAME_RE = re.compile(r"^[a-z0-9_-]+$")


def normalize_username(raw: str) -> str:
    """Lowercase, trim, and validate a username. Raises ``ValueError`` if it breaks the policy."""
    value = raw.strip().lower()
    if not (USERNAME_MIN <= len(value) <= USERNAME_MAX):
        raise ValueError(f"Username must be {USERNAME_MIN}-{USERNAME_MAX} characters.")
    if not USERNAME_RE.match(value):
        raise ValueError("Username may contain only letters, numbers, hyphen and underscore.")
    return value


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    username: str
    locale: str


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str
    locale: Locale = "en"

    @field_validator("username")
    @classmethod
    def _normalize(cls, v: str) -> str:
        return normalize_username(v)


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    locale: Locale | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str
    password: str
