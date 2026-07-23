# SPDX-License-Identifier: AGPL-3.0-only
"""Shared FastAPI dependencies."""

from __future__ import annotations

from fastapi import Request

from tradeschool.config import Settings


def app_settings(request: Request) -> Settings:
    """The Settings bound to the running app (tests inject their own)."""
    settings: Settings = request.app.state.settings
    return settings
