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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="tradeschool", description="TradeSchool management CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("migrate", help="Apply database migrations (alembic upgrade head)")
    sub.add_parser("sync", help="Reconcile the course manifest into the database")

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _cmd_migrate()
    if args.command == "sync":
        return _cmd_sync()
    parser.error(f"unknown command {args.command!r}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
