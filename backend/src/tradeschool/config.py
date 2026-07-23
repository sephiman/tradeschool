# SPDX-License-Identifier: AGPL-3.0-only
"""Application configuration via environment variables (pydantic-settings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_content_dir() -> Path:
    """Repo `content/` in development; overridden by CONTENT_DIR in the container."""
    # config.py -> tradeschool -> src -> backend -> repo root
    return Path(__file__).resolve().parents[3] / "content"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Database (externally-managed Postgres on the shared Docker network) ---
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "tradeschool"
    db_username: str = "tradeschool"
    db_password: str = "change-me"

    # --- Session cookie (fastapi-users cookie transport + database strategy) ---
    cookie_secure: bool = True
    session_cookie_name: str = "tradeschool_session"
    session_max_age: int = 60 * 60 * 24 * 30  # 30 days, in seconds

    # --- Rate limiting (slowapi) on auth endpoints ---
    rate_limit_enabled: bool = True
    login_rate_limit: str = "10/minute"
    register_rate_limit: str = "5/minute"

    # Secret for fastapi-users reset/verify token flows (unused in v1 — no such endpoints —
    # but BaseUserManager requires a value).
    auth_secret: str = "change-me"

    # --- Content / manifest ---
    content_dir: Path = _default_content_dir()
    sync_content_on_startup: bool = True
    run_migrations_on_startup: bool = True

    # --- Operational ---
    dev_mode: bool = False
    default_locale: str = "en"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.db_username}:{self.db_password}"
            f"@{self.db_host}:{self.db_port}/{self.db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
