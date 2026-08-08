# SPDX-License-Identifier: AGPL-3.0-only
"""FastAPI application factory and startup lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import APIRouter, Depends, FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from tradeschool import health
from tradeschool.attempts.router import router as attempts_router
from tradeschool.auth.router import router as auth_router
from tradeschool.config import Settings, get_settings
from tradeschool.content.router import course_router
from tradeschool.content.router import router as content_router
from tradeschool.db import dispose_engine, init_engine
from tradeschool.deps import current_course
from tradeschool.errors import register_exception_handlers
from tradeschool.exams.router import router as exams_router
from tradeschool.ratelimit import limiter
from tradeschool.stats.router import router as stats_router

logger = logging.getLogger("tradeschool")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
    settings: Settings = app.state.settings
    init_engine(settings.database_url)

    if settings.run_migrations_on_startup:
        from tradeschool.migrations import run_migrations

        logger.info("Running database migrations…")
        # Alembic's async env calls asyncio.run internally, which cannot run inside this
        # already-running loop; execute it in a worker thread.
        await asyncio.to_thread(run_migrations, settings.database_url)

    # Load the course registry (validates manifest + content parity) and expose it for serving.
    from tradeschool.content.registry import load_registry

    app.state.registry = load_registry(settings.content_dir)

    if settings.sync_content_on_startup:
        from tradeschool.content.sync import reconcile
        from tradeschool.db import get_sessionmaker

        async with get_sessionmaker()() as session:
            await reconcile(app.state.registry.manifest, session)

    yield

    await dispose_engine()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(
        title="TradeSchool",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.dev_mode else None,
        openapi_url="/api/openapi.json" if settings.dev_mode else None,
    )
    app.state.settings = settings

    # Rate limiting (slowapi). The limiter is a shared singleton; toggle it per app.
    limiter.enabled = settings.rate_limit_enabled
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

    register_exception_handlers(app)

    api = APIRouter(prefix="/api")
    # Genuinely global: an account is not per-course, and health/version describe the service.
    api.include_router(health.router)
    api.include_router(auth_router, prefix="/auth")

    # Everything whose data belongs to a course. Mounted TWICE from one definition: canonically
    # under /api/courses/{course}/…, and unscoped as a deprecated alias that resolves to the single
    # course. `current_course` reads the segment off path_params, so the same handlers serve both.
    course_owned = (content_router, attempts_router, stats_router, exams_router)

    scoped = APIRouter(prefix="/courses/{course}", dependencies=[Depends(current_course)])
    for router in course_owned:
        scoped.include_router(router)
    api.include_router(scoped)
    # Included with the prefix rather than nested: the course tree's own path is "", and FastAPI
    # rejects an empty path under an empty include-prefix.
    api.include_router(
        course_router, prefix="/courses/{course}", dependencies=[Depends(current_course)]
    )

    # The alias is for clients we do not control; ours use the scoped URLs. Hidden from the schema
    # so /api/docs shows one canonical URL per endpoint (and so operation ids stay unique).
    # `deprecated=True` is deliberately NOT set here: the two mounts share one router, so it would
    # not reach the route object anyway. The alias is marked on the way out, by _deprecation_headers.
    alias = APIRouter(include_in_schema=False)
    for router in course_owned:
        alias.include_router(router)
    api.include_router(alias)
    # Restores today's /api/course, /api/course/export, /api/course/print/exercises.
    api.include_router(course_router, prefix="/course", include_in_schema=False)

    if settings.dev_mode:
        from tradeschool.dev.router import router as dev_router

        # Dev-gated tooling, not a public surface: left unscoped deliberately.
        api.include_router(dev_router, prefix="/dev")
    app.include_router(api)

    @app.middleware("http")
    async def _deprecation_headers(request: Request, call_next: Any) -> Any:
        """RFC 8594 headers on the unscoped aliases, pointing at the course-scoped successor.

        Middleware rather than a dependency because some handlers return a Response object directly
        (the export does), and headers set on an injected Response never reach those.

        Decided from the PATH, not from a route flag: the two mounts share one router, so FastAPI
        hands both the same route object and per-mount metadata has nowhere to live on it.
        """
        response = await call_next(request)
        if request.scope.get("route") is not None and _is_alias(request.url.path):
            slug = request.app.state.registry.manifest.course.id
            response.headers["Deprecation"] = "true"
            response.headers["Link"] = (
                f'<{_canonical_path(request.url.path, slug)}>; rel="successor-version"'
            )
        return response

    return app


# Everything under /api that does NOT belong to a course. An unscoped path outside this set is an
# alias for the single course.
_GLOBAL_PREFIXES = (
    "/api/auth",
    "/api/health",
    "/api/version",
    "/api/dev",
    "/api/docs",
    "/api/openapi.json",
)


def _is_alias(path: str) -> bool:
    if not path.startswith("/api/") or path.startswith("/api/courses/"):
        return False
    return not path.startswith(_GLOBAL_PREFIXES)


def _canonical_path(path: str, slug: str) -> str:
    """Where an unscoped alias moved to: /api/course/export -> /api/courses/{slug}/export."""
    rest = path[len("/api/course") :] if path.startswith("/api/course") else path[len("/api") :]
    return f"/api/courses/{slug}{rest}"


async def _rate_limit_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        status_code=429,
        content={"code": "RATE_LIMITED", "message": "Too many requests. Please slow down."},
    )


app = create_app()
