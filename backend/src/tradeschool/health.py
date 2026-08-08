# SPDX-License-Identifier: AGPL-3.0-only
"""Liveness/readiness endpoint. Readiness verifies Postgres connectivity."""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, FastAPI, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.db import get_async_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


class VersionResponse(BaseModel):
    """What this container was built from. `unknown` means the build did not pass the args."""

    commit: str
    builtAt: str
    routes: int


def _api_path_count(app: FastAPI) -> int:
    """How many API paths this build registers.

    Counted from the OpenAPI schema, not from `app.routes`: the latter does NOT flatten — an included
    router stays one opaque `_IncludedRouter` entry, so reading it directly reports 5 for the whole
    service. `app.openapi()` is public, works even when `openapi_url` is disabled in production, and
    FastAPI caches the schema after the first call.
    """
    return len(app.openapi().get("paths", {}))


@router.get("/version", response_model=VersionResponse)
async def version(request: Request) -> VersionResponse:
    """Which build is actually serving — unauthenticated, so it answers before you can log in.

    Baked by the Dockerfile's GIT_COMMIT/BUILD_TIME args. `routes` is the registered API path count:
    a cheap tell that the image carries the endpoints you think it does, without listing them all.
    """
    return VersionResponse(
        commit=os.environ.get("GIT_COMMIT", "unknown"),
        builtAt=os.environ.get("BUILD_TIME", "unknown"),
        routes=_api_path_count(request.app),
    )


@router.get("/health", response_model=HealthResponse)
async def health(session: Annotated[AsyncSession, Depends(get_async_session)]) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")
