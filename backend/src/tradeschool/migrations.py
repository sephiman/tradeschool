# SPDX-License-Identifier: AGPL-3.0-only
"""Run Alembic migrations programmatically (used by the startup lifespan and the CLI)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend


def alembic_config(database_url: str) -> Config:
    cfg = Config(str(_BACKEND_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    # Alembic env.py reads this; asyncpg URL is handled by the async env.
    cfg.set_main_option("sqlalchemy.url", database_url)
    return cfg


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")
