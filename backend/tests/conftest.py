# SPDX-License-Identifier: AGPL-3.0-only
"""Shared fixtures: Postgres via testcontainers, migrations once, a per-test client, truncation between."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager

import pytest
import pytest_asyncio
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from testcontainers.postgres import PostgresContainer

# Import every model so Base.metadata is complete for truncation.
import tradeschool.models  # noqa: F401
from tradeschool.config import Settings
from tradeschool.db import Base, get_sessionmaker
from tradeschool.main import create_app
from tradeschool.migrations import run_migrations
from tradeschool.ratelimit import limiter

_DB = "tradeschool_test"
_USER = "tradeschool"
_PASSWORD = "tradeschool"


@pytest.fixture(scope="session")
def postgres_container() -> Generator[PostgresContainer]:
    with PostgresContainer(
        "postgres:17-alpine", username=_USER, password=_PASSWORD, dbname=_DB
    ) as pg:
        yield pg


@pytest.fixture(scope="session")
def settings(postgres_container: PostgresContainer) -> Settings:
    return Settings(
        db_host=postgres_container.get_container_host_ip(),
        db_port=int(postgres_container.get_exposed_port(5432)),
        db_name=_DB,
        db_username=_USER,
        db_password=_PASSWORD,
        # Migrations are applied once by the `_migrated` fixture (outside any running loop);
        # the per-test app must not try to run them from within the lifespan's event loop.
        run_migrations_on_startup=False,
        sync_content_on_startup=False,
        dev_mode=True,
        cookie_secure=False,
        # Off by default so functional tests aren't throttled; the rate-limit test flips it on.
        rate_limit_enabled=False,
    )


@pytest.fixture(scope="session")
def _migrated(settings: Settings) -> bool:
    # alembic's async env calls asyncio.run internally, so this must run from a sync context.
    run_migrations(settings.database_url)
    return True


async def _truncate_all() -> None:
    tables = list(Base.metadata.sorted_tables)
    if not tables:
        return
    names = ", ".join(f'"{t.name}"' for t in tables)
    async with get_sessionmaker()() as session:
        await session.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))
        await session.commit()


@asynccontextmanager
async def _build_client(settings: Settings, reconcile_content: bool = False) -> AsyncGenerator[AsyncClient]:
    app = create_app(settings)
    async with LifespanManager(app):
        await _truncate_all()
        if reconcile_content:
            # Reconcile AFTER truncation so the skeleton survives for FK-backed progress writes.
            from tradeschool.content.sync import reconcile

            async with get_sessionmaker()() as db:
                await reconcile(app.state.registry.manifest, db)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as http:
            yield http


@pytest_asyncio.fixture
async def client(settings: Settings, _migrated: bool) -> AsyncGenerator[AsyncClient]:
    async with _build_client(settings) as http:
        yield http


@pytest_asyncio.fixture
async def content_client(settings: Settings, _migrated: bool) -> AsyncGenerator[AsyncClient]:
    """Client with the real course manifest reconciled into the DB (for content endpoints)."""
    async with _build_client(settings, reconcile_content=True) as http:
        yield http


@pytest_asyncio.fixture
async def rl_client(settings: Settings, _migrated: bool) -> AsyncGenerator[AsyncClient]:
    """Client with rate limiting enabled (fresh limiter storage) for the throttling test."""
    rl_settings = settings.model_copy(update={"rate_limit_enabled": True})
    async with _build_client(rl_settings) as http:
        limiter.reset()
        yield http


@pytest_asyncio.fixture
async def session(client: AsyncClient) -> AsyncGenerator[AsyncSession]:
    """A live DB session bound to the same engine the app uses (for seeding/asserting)."""
    async with get_sessionmaker()() as db:
        yield db
