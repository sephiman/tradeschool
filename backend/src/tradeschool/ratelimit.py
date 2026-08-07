# SPDX-License-Identifier: AGPL-3.0-only
"""Shared slowapi limiter, keyed by the real client IP (X-Forwarded-For's first hop behind nginx)."""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=_client_ip)
