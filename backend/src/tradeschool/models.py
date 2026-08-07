# SPDX-License-Identifier: AGPL-3.0-only
"""Central import point so `Base.metadata` sees every table — imported by alembic and the tests."""

from __future__ import annotations

# Domain models are imported for their side effect of registering on Base.metadata.
from tradeschool.attempts import models as _attempt_models  # noqa: F401
from tradeschool.auth import models as _auth_models  # noqa: F401
from tradeschool.content import models as _content_models  # noqa: F401
from tradeschool.db import Base
from tradeschool.exams import models as _exam_models  # noqa: F401

__all__ = ["Base"]
