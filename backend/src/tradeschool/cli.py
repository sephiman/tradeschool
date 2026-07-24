# SPDX-License-Identifier: AGPL-3.0-only
"""Management CLI: `tradeschool <command>`."""

from __future__ import annotations

import argparse
import asyncio
import sys

from tradeschool.config import get_settings


def _cmd_migrate() -> int:
    from tradeschool.migrations import run_migrations

    settings = get_settings()
    run_migrations(settings.database_url)
    print("Migrations applied.")
    return 0


def _cmd_sync() -> int:
    from tradeschool.content.sync import sync_content_cli

    summary = asyncio.run(sync_content_cli(get_settings()))
    print(summary)
    return 0


def _cmd_reset_password(username: str) -> int:
    """Admin password reset (self-service reset is gone with email). Prompts twice, Argon2-hashes."""
    import getpass

    from sqlalchemy import func, select

    from tradeschool.auth.manager import MIN_PASSWORD_LENGTH, password_helper
    from tradeschool.auth.models import User
    from tradeschool.db import dispose_engine, get_sessionmaker, init_engine

    lookup = username.strip().lower()

    async def run() -> int:
        init_engine(get_settings().database_url)
        try:
            async with get_sessionmaker()() as session:
                user = (
                    await session.scalars(
                        select(User).where(func.lower(User.username) == lookup)
                    )
                ).first()
                if user is None:
                    print(f"No user with username {lookup!r}.", file=sys.stderr)
                    return 1
                new = getpass.getpass(f"New password for {user.username!r}: ")
                confirm = getpass.getpass("Confirm new password: ")
                if new != confirm:
                    print("Passwords do not match.", file=sys.stderr)
                    return 1
                if len(new) < MIN_PASSWORD_LENGTH:
                    print(
                        f"Password must be at least {MIN_PASSWORD_LENGTH} characters.",
                        file=sys.stderr,
                    )
                    return 1
                user.hashed_password = password_helper.hash(new)
                await session.commit()
                print(f"Password updated for {user.username!r}.")
                return 0
        finally:
            await dispose_engine()

    return asyncio.run(run())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradeschool", description="TradeSchool management CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations (alembic upgrade head)")
    sub.add_parser("sync", help="Reconcile the course manifest into the database")
    reset = sub.add_parser("reset-password", help="Set a user's password (prompts for the new one)")
    reset.add_argument("username", help="Username of the account to reset")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _cmd_migrate()
    if args.command == "sync":
        return _cmd_sync()
    if args.command == "reset-password":
        return _cmd_reset_password(args.username)
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
