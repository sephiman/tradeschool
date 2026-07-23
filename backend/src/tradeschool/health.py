# SPDX-License-Identifier: AGPL-3.0-only
"""Liveness/readiness endpoint. Readiness verifies Postgres connectivity."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tradeschool.db import get_async_session

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    database: str


@router.get("/health", response_model=HealthResponse)
async def health(session: Annotated[AsyncSession, Depends(get_async_session)]) -> HealthResponse:
    await session.execute(text("SELECT 1"))
    return HealthResponse(status="ok", database="ok")
