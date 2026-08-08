# SPDX-License-Identifier: AGPL-3.0-only
"""Shared FastAPI dependencies."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from tradeschool.config import Settings
from tradeschool.content.registry import CourseRegistry
from tradeschool.errors import AppError


def app_settings(request: Request) -> Settings:
    """The Settings bound to the running app (tests inject their own)."""
    settings: Settings = request.app.state.settings
    return settings


def current_course(request: Request) -> str:
    """The course this request is about, from `/api/courses/{course}/…`.

    Read off `request.path_params` rather than declared as a handler argument, so the SAME router
    can serve both mounts: canonical (the segment is there and is validated) and the deprecated
    unscoped alias (no segment, so it resolves to the single course). Declaring it as a parameter
    would turn it into a stray query param on the alias mount.
    """
    registry: CourseRegistry = request.app.state.registry
    only: str = registry.manifest.course.id
    raw = request.path_params.get("course")
    if raw is None:
        return only  # unscoped alias
    slug = str(raw)
    if slug != only:
        raise AppError("COURSE_NOT_FOUND", f"No course {slug!r}.", status_code=404)
    return slug


CourseId = Annotated[str, Depends(current_course)]
