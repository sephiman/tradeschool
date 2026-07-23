# SPDX-License-Identifier: AGPL-3.0-only
"""FastAPI application factory and startup lifespan."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from starlette.responses import JSONResponse

from tradeschool import health
from tradeschool.attempts.router import router as attempts_router
from tradeschool.auth.router import router as auth_router
from tradeschool.config import Settings, get_settings
from tradeschool.content.router import router as content_router
from tradeschool.db import dispose_engine, init_engine
from tradeschool.errors import register_exception_handlers
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
    api.include_router(health.router)
    api.include_router(auth_router, prefix="/auth")
    api.include_router(content_router)
    api.include_router(attempts_router)
    api.include_router(stats_router)
    if settings.dev_mode:
        from tradeschool.dev.router import router as dev_router

        api.include_router(dev_router, prefix="/dev")
    app.include_router(api)

    return app


async def _rate_limit_handler(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimitExceeded)
    return JSONResponse(
        status_code=429,
        content={"code": "RATE_LIMITED", "message": "Too many requests. Please slow down."},
    )


app = create_app()
