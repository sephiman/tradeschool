# SPDX-License-Identifier: AGPL-3.0-only
"""Central import point so `Base.metadata` sees every table.

Alembic's env.py and the test schema bootstrap both import this module; each domain package
registers its ORM models here as they are added.
"""

from __future__ import annotations

# Domain models are imported for their side effect of registering on Base.metadata.
from tradeschool.attempts import models as _attempt_models  # noqa: F401
from tradeschool.auth import models as _auth_models  # noqa: F401
from tradeschool.content import models as _content_models  # noqa: F401
from tradeschool.db import Base
from tradeschool.exams import models as _exam_models  # noqa: F401

__all__ = ["Base"]
