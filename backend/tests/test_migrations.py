# SPDX-License-Identifier: AGPL-3.0-only
"""Migrations run for their schema, not for their side effects.

`logging.config.fileConfig` defaults `disable_existing_loggers` to True, silently killing the whole
`tradeschool.*` tree for the life of the process — and the app migrates from its startup lifespan.
"""

from __future__ import annotations

import logging

import tradeschool.content.print_export  # noqa: F401  # the module whose logger must survive


def test_migrations_leave_application_logging_alone(_migrated: bool) -> None:
    for name in ("tradeschool", "tradeschool.auth", "tradeschool.content"):
        logger = logging.getLogger(name)
        assert not logger.disabled, f"migrations silenced {name}"
        assert logger.propagate, f"migrations cut {name} off from the root handlers"
